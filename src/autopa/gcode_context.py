"""Safe G-code context instrumentation for synchronized AutoPA analysis."""
import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path


CONTEXT_EVENT = "context"
CONTEXT_FORMAT_VERSION = 1
PA_ELIGIBLE_FEATURES = {
    "external_perimeter",
    "internal_perimeter",
    "infill",
    "solid_infill",
    "gap_fill",
}

_MOVE_RE = re.compile(r"^\s*G(?:0|1)(?:\s|$)", re.IGNORECASE)
_LAYER_RE = re.compile(r"^\s*;\s*LAYER\s*:\s*(-?\d+)", re.IGNORECASE)
_LAYER_NUM_RE = re.compile(
    r"^\s*;\s*layer\s+num(?:/total_layer_count)?\s*:\s*(-?\d+)",
    re.IGNORECASE,
)
_Z_RE = re.compile(
    r"^\s*;\s*(?:Z|HEIGHT)\s*:\s*(-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_TYPE_RE = re.compile(r"^\s*;\s*TYPE\s*:\s*(.+?)\s*$", re.IGNORECASE)
_PRUSA_FEATURE_RE = re.compile(
    r"^\s*;\s*(?:FEATURE|PRINTING_FEATURE)\s*:\s*(.+?)\s*$",
    re.IGNORECASE,
)
_OBJECT_START_RE = re.compile(
    r"^\s*EXCLUDE_OBJECT_START\s+.*?\bNAME=(?:\"([^\"]+)\"|(\S+))",
    re.IGNORECASE,
)
_OBJECT_END_RE = re.compile(r"^\s*EXCLUDE_OBJECT_END(?:\s|$)", re.IGNORECASE)
_PRINTING_OBJECT_RE = re.compile(
    r"^\s*;\s*printing object\s+(.+?)\s*$", re.IGNORECASE)


def normalize_feature(value):
    """Map common Prusa/Orca/SuperSlicer/Cura labels to stable names."""
    text = re.sub(r"[_-]+", " ", str(value or "").strip().lower())
    text = re.sub(r"\s+", " ", text)
    if not text:
        return "unknown"
    if any(token in text for token in (
            "external perimeter", "outer perimeter", "outer wall",
            "wall outer")):
        return "external_perimeter"
    if any(token in text for token in (
            "internal perimeter", "inner perimeter", "inner wall",
            "wall inner")):
        return "internal_perimeter"
    if "bridge" in text or "overhang" in text:
        return "bridge"
    if "support" in text:
        return "support"
    if any(token in text for token in (
            "top solid", "bottom solid", "solid infill",
            "top surface", "bottom surface")):
        return "solid_infill"
    if "gap fill" in text:
        return "gap_fill"
    if "infill" in text or "internal solid" in text:
        return "infill"
    if "perimeter" in text or text == "wall":
        return "internal_perimeter"
    if "ironing" in text:
        return "ironing"
    if any(token in text for token in (
            "skirt", "brim", "prime tower", "wipe tower")):
        return "skirt_brim"
    return "unknown"


def context_payload(layer=None, z_mm=None, feature="unknown", object_name=None,
                    source_line=None):
    feature = normalize_feature(feature)
    safe_object = (
        str(object_name).strip()[:96] if object_name is not None else None)
    eligible = feature in PA_ELIGIBLE_FEATURES
    return {
        "version": CONTEXT_FORMAT_VERSION,
        "layer": int(layer) if layer is not None else None,
        "z_mm": float(z_mm) if z_mm is not None else None,
        "feature": feature,
        "object": safe_object or None,
        "source_line": (
            int(source_line) if source_line is not None else None),
        "pa_eligible": eligible,
        "eligibility_reason": (
            "eligible_extrusion_feature"
            if eligible else
            "feature_not_validated_for_pa"
            if feature != "unknown" else
            "feature_unknown"),
    }


def encode_context_marker(context):
    compact = {
        "v": CONTEXT_FORMAT_VERSION,
        "l": context.get("layer"),
        "z": context.get("z_mm"),
        "f": normalize_feature(context.get("feature")),
        "o": context.get("object"),
        "n": context.get("source_line"),
    }
    raw = json.dumps(
        compact, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_context_marker(value):
    """Decode one marker. Invalid/untrusted values fail closed."""
    try:
        encoded = str(value).strip()
        encoded += "=" * (-len(encoded) % 4)
        compact = json.loads(
            base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8"))
        if compact.get("v") != CONTEXT_FORMAT_VERSION:
            raise ValueError("unsupported context marker version")
        layer = compact.get("l")
        z_mm = compact.get("z")
        if layer is not None and (
                isinstance(layer, bool) or not isinstance(layer, int)):
            raise ValueError("invalid layer")
        if z_mm is not None and (
                isinstance(z_mm, bool)
                or not isinstance(z_mm, (int, float))):
            raise ValueError("invalid Z height")
        source_line = compact.get("n")
        if source_line is not None and (
                isinstance(source_line, bool)
                or not isinstance(source_line, int)
                or source_line < 1):
            raise ValueError("invalid source line")
        return context_payload(
            layer=layer,
            z_mm=z_mm,
            feature=compact.get("f"),
            object_name=compact.get("o"),
            source_line=source_line)
    except (ValueError, TypeError, KeyError, UnicodeError, binascii.Error,
            json.JSONDecodeError) as exc:
        raise ValueError("invalid AutoPA context marker") from exc


class ContextTimeline:
    """Resolve queued Klipper context events against executed print_time."""

    def __init__(self, max_transitions=512):
        self.max_transitions = max_transitions
        self._transitions = []
        self._seen_sequences = set()

    def observe(self, events):
        for event in events or ():
            if event.get("event") != CONTEXT_EVENT:
                continue
            sequence = event.get("sequence")
            print_time = event.get("print_time")
            if sequence in self._seen_sequences:
                continue
            if (isinstance(print_time, bool)
                    or not isinstance(print_time, (int, float))):
                continue
            try:
                context = decode_context_marker(event.get("value"))
            except ValueError:
                continue
            context["sequence"] = sequence
            context["print_time"] = float(print_time)
            self._transitions.append(context)
            if sequence is not None:
                self._seen_sequences.add(sequence)
        self._transitions.sort(
            key=lambda item: (item["print_time"], item.get("sequence") or -1))
        if len(self._transitions) > self.max_transitions:
            removed = self._transitions[:-self.max_transitions]
            self._transitions = self._transitions[-self.max_transitions:]
            for item in removed:
                self._seen_sequences.discard(item.get("sequence"))

    def resolve(self, print_time):
        if (isinstance(print_time, bool)
                or not isinstance(print_time, (int, float))):
            return {
                **context_payload(),
                "active": False,
                "eligibility_reason": "print_time_missing",
            }
        current = None
        for transition in reversed(self._transitions):
            if transition["print_time"] <= float(print_time) + 1e-9:
                current = transition
                break
        if current is None:
            return {
                **context_payload(),
                "active": False,
                "eligibility_reason": "context_marker_pending_or_missing",
            }
        return {**current, "active": True}


class GCodeContextParser:
    """Track semantic slicer context without interpreting printer macros."""

    def __init__(self):
        self.layer = None
        self.z_mm = None
        self.feature = "unknown"
        self.object_name = None
        self._saw_explicit_layer = False
        self.dirty = True

    def feed(self, line):
        changed = False
        match = _LAYER_RE.match(line) or _LAYER_NUM_RE.match(line)
        if match:
            layer = int(match.group(1))
            self._saw_explicit_layer = True
            if layer != self.layer:
                self.layer = layer
                changed = True
        elif re.match(r"^\s*;\s*LAYER_CHANGE\s*$", line, re.IGNORECASE):
            if not self._saw_explicit_layer:
                layer = 0 if self.layer is None else self.layer + 1
                if layer != self.layer:
                    self.layer = layer
                    changed = True

        match = _Z_RE.match(line)
        if match:
            z_mm = float(match.group(1))
            if z_mm != self.z_mm:
                self.z_mm = z_mm
                changed = True

        match = _TYPE_RE.match(line) or _PRUSA_FEATURE_RE.match(line)
        if match:
            feature = normalize_feature(match.group(1))
            if feature != self.feature:
                self.feature = feature
                changed = True

        match = _OBJECT_START_RE.match(line)
        if match:
            object_name = (match.group(1) or match.group(2)).strip()[:96]
            if object_name != self.object_name:
                self.object_name = object_name
                changed = True
        elif _OBJECT_END_RE.match(line):
            if self.object_name is not None:
                self.object_name = None
                changed = True
        else:
            match = _PRINTING_OBJECT_RE.match(line)
            if match:
                object_name = match.group(1).strip().strip('"')[:96]
                if object_name != self.object_name:
                    self.object_name = object_name
                    changed = True

        self.dirty = self.dirty or changed
        return changed

    def context(self):
        return context_payload(
            self.layer, self.z_mm, self.feature, self.object_name)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def instrument_gcode(source_path, output_path, overwrite=False):
    """Create a distinct instrumented copy and return a verification manifest."""
    source = Path(source_path).resolve()
    output = Path(output_path).resolve()
    if source == output:
        raise ValueError("input and output G-code must be different files")
    if not source.is_file():
        raise FileNotFoundError(source)
    sidecar = Path(str(output) + ".context.json")
    if output.exists() and not overwrite:
        raise FileExistsError(output)
    if sidecar.exists() and not overwrite:
        raise FileExistsError(sidecar)
    output.parent.mkdir(parents=True, exist_ok=True)
    source_hash = _sha256(source)

    parser = GCodeContextParser()
    marker_count = 0
    layers = set()
    features = set()
    objects = set()
    temporary_name = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=output.name + ".", suffix=".tmp", dir=str(output.parent))
        with os.fdopen(descriptor, "wb") as destination, source.open("rb") as src:
            newline = b"\n"
            for line_number, raw_line in enumerate(src, 1):
                if raw_line.endswith(b"\r\n"):
                    newline = b"\r\n"
                elif raw_line.endswith(b"\n"):
                    newline = b"\n"
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                if re.match(
                        r"^\s*AUTOPA_MARK\s+.*\bEVENT=context(?:\s|$)",
                        line, re.IGNORECASE):
                    raise ValueError("G-code is already AutoPA-instrumented")
                parser.feed(line)
                if _MOVE_RE.match(line) and parser.dirty:
                    context = parser.context()
                    context["source_line"] = line_number
                    marker = (
                        "AUTOPA_MARK EVENT=%s VALUE=%s" % (
                            CONTEXT_EVENT, encode_context_marker(context)))
                    destination.write(marker.encode("ascii") + newline)
                    parser.dirty = False
                    marker_count += 1
                    if context["layer"] is not None:
                        layers.add(context["layer"])
                    features.add(context["feature"])
                    if context["object"]:
                        objects.add(context["object"])
                destination.write(raw_line)
            destination.flush()
            os.fsync(destination.fileno())
        if marker_count == 0:
            raise ValueError("G-code contains no G0/G1 movement")
        if _sha256(source) != source_hash:
            raise RuntimeError(
                "source G-code changed while it was being instrumented")
        os.replace(temporary_name, output)
        temporary_name = None
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)

    manifest = {
        "format_version": CONTEXT_FORMAT_VERSION,
        "source": str(source),
        "output": str(output),
        "source_sha256": source_hash,
        "output_sha256": _sha256(output),
        "marker_count": marker_count,
        "layers": sorted(layers),
        "features": sorted(features),
        "objects": sorted(objects),
        "original_modified": False,
        "runtime_policy": "context_only_fail_open",
    }
    descriptor, sidecar_temporary = tempfile.mkstemp(
        prefix=sidecar.name + ".", suffix=".tmp", dir=str(sidecar.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                manifest, handle, ensure_ascii=False, indent=2,
                sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(sidecar_temporary, sidecar)
    finally:
        if os.path.exists(sidecar_temporary):
            os.unlink(sidecar_temporary)
    manifest["sidecar"] = str(sidecar)
    return manifest


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Create a separate AutoPA-instrumented G-code copy. "
            "The source file is never modified."))
    parser.add_argument("input", help="Original slicer G-code")
    parser.add_argument("output", help="New instrumented G-code")
    parser.add_argument(
        "--force", action="store_true",
        help="Replace an existing output file; never replaces the input")
    args = parser.parse_args()
    print(json.dumps(
        instrument_gcode(args.input, args.output, overwrite=args.force),
        ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

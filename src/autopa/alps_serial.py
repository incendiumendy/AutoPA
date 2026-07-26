"""Read force samples from a Mellow FLY-ALPS running factory firmware."""
import argparse
import csv
import dataclasses
import os
import re
import select
import time
from typing import Optional


VERSION_RE = re.compile(r"version:(\S+)", re.IGNORECASE)
V1_RAW_RE = re.compile(r"^a=(-?\d+)$")
V1_FILTERED_RE = re.compile(r"^b=(-?\d+)$")
V2_SAMPLE_RE = re.compile(r"^a=(-?\d+),b=(-?\d+)$")


@dataclasses.dataclass(frozen=True)
class AlpsSample:
    host_monotonic_ns: int
    raw: Optional[int]
    filtered: Optional[int]


class AlpsLineParser:
    """Parse both known generations of the Mellow text protocol."""

    def __init__(self):
        self.pending_raw = None

    def parse(self, line, timestamp_ns):
        line = line.strip()
        match = V2_SAMPLE_RE.fullmatch(line)
        if match:
            self.pending_raw = None
            return AlpsSample(timestamp_ns, int(match[1]), int(match[2]))
        match = V1_RAW_RE.fullmatch(line)
        if match:
            self.pending_raw = (timestamp_ns, int(match[1]))
            return None
        match = V1_FILTERED_RE.fullmatch(line)
        if match:
            filtered = int(match[1])
            if self.pending_raw is None:
                return AlpsSample(timestamp_ns, None, filtered)
            raw_time, raw = self.pending_raw
            self.pending_raw = None
            return AlpsSample(raw_time, raw, filtered)
        return None


def _is_legacy_version(version):
    return version in ("1.0", "1.0.0")


class AlpsSerial:
    def __init__(self, device, baud=115200):
        if baud != 115200:
            raise ValueError("Factory ALPS protocol is verified only at 115200")
        self.device = device
        self.baud = baud
        self.fd = None
        self.buffer = bytearray()
        self.parser = AlpsLineParser()
        self.version = None

    def open(self):
        try:
            import termios
            import tty
        except ImportError as exc:
            raise RuntimeError(
                "FLY-ALPS serial capture requires a POSIX host") from exc
        self.fd = os.open(
            self.device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        tty.setraw(self.fd, termios.TCSANOW)
        attrs = termios.tcgetattr(self.fd)
        attrs[4] = termios.B115200
        attrs[5] = termios.B115200
        attrs[2] = (attrs[2] & ~termios.CSIZE) | termios.CS8
        attrs[2] &= ~(termios.PARENB | termios.CSTOPB)
        attrs[2] |= termios.CLOCAL | termios.CREAD
        termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
        termios.tcflush(self.fd, termios.TCIOFLUSH)

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def _write(self, value):
        if self.fd is None:
            raise RuntimeError("ALPS serial device is not open")
        payload = value.encode("ascii")
        offset = 0
        while offset < len(payload):
            _, writable, _ = select.select([], [self.fd], [], 1.0)
            if not writable:
                raise TimeoutError("Timed out writing to ALPS")
            offset += os.write(self.fd, payload[offset:])

    def _read_lines(self, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            remaining = max(0.0, deadline - time.monotonic())
            readable, _, _ = select.select([self.fd], [], [], remaining)
            if not readable:
                return
            chunk = os.read(self.fd, 4096)
            if not chunk:
                return
            self.buffer.extend(chunk)
            while b"\n" in self.buffer:
                raw_line, _, rest = self.buffer.partition(b"\n")
                self.buffer = bytearray(rest)
                yield raw_line.decode("ascii", errors="replace").strip()

    def detect_version(self, timeout=0.75):
        self._write("version\n")
        for line in self._read_lines(timeout):
            match = VERSION_RE.search(line)
            if match:
                self.version = match[1]
                return self.version
        # The web tool uses the same fallback for firmware 1.0.
        self.version = "1.0"
        return self.version

    def start_stream(self):
        if self.version is None:
            self.detect_version()
        self._write("v" if _is_legacy_version(self.version) else "v\n")

    def stop_stream(self):
        if self.fd is None:
            return
        version = self.version or "1.0"
        self._write("uv" if _is_legacy_version(version) else "uv\n")

    def samples(self, duration=None):
        started = time.monotonic()
        while duration is None or time.monotonic() - started < duration:
            timeout = 0.5
            if duration is not None:
                timeout = min(timeout, max(
                    0.0, duration - (time.monotonic() - started)))
            for line in self._read_lines(timeout):
                timestamp_ns = time.monotonic_ns()
                sample = self.parser.parse(line, timestamp_ns)
                if sample is not None:
                    yield sample

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            self.stop_stream()
        finally:
            self.close()


def capture(device, output, duration):
    with AlpsSerial(device) as alps, open(
            output, "w", newline="", buffering=1024 * 1024) as handle:
        writer = csv.writer(handle)
        writer.writerow(("host_monotonic_ns", "raw", "filtered"))
        version = alps.detect_version()
        alps.start_stream()
        count = 0
        for sample in alps.samples(duration):
            writer.writerow(dataclasses.astuple(sample))
            count += 1
    return version, count


def main():
    parser = argparse.ArgumentParser(
        description="Capture factory-firmware FLY-ALPS measurements")
    parser.add_argument("--device", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--duration", type=float, default=10.0)
    args = parser.parse_args()
    version, count = capture(args.device, args.output, args.duration)
    print("FLY-ALPS firmware %s: captured %d samples" % (version, count))


if __name__ == "__main__":
    main()

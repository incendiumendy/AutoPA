"""Filename-triggered, independently locked chamber-filter controller."""
import json
import math
import os
import re
import threading
import time
import urllib.request


ACTIVE_PRINT_STATES = {"printing", "paused"}
FAN_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
MAX_PROFILES = 50


def _finite(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value))


def validated_profiles(values, available_fans):
    if not isinstance(values, list):
        raise ValueError("profiles must be an array")
    if len(values) > MAX_PROFILES:
        raise ValueError("too many material profiles")
    available_fans = set(available_fans)
    profiles = []
    seen_tags = set()
    for value in values:
        if not isinstance(value, dict):
            raise ValueError("each material profile must be an object")
        enabled = value.get("filter_enabled", False)
        if not isinstance(enabled, bool):
            raise ValueError("filter_enabled must be a boolean")
        tag = str(value.get("filter_tag", "")).strip()
        fan = str(value.get("filter_fan", "")).strip()
        speed = value.get("filter_speed_percent", 100)
        post_run = value.get("filter_post_run_minutes", 20)
        if enabled:
            if not 2 <= len(tag) <= 48:
                raise ValueError(
                    "enabled filter tags must contain 2 to 48 characters")
            if tag.casefold() in seen_tags:
                raise ValueError("filter tags must be unique")
            if not FAN_NAME_RE.fullmatch(fan):
                raise ValueError("invalid chamber filter fan name")
            if fan not in available_fans:
                raise ValueError(
                    "unknown fan_generic object: %s" % fan)
            if not _finite(speed) or not 10 <= float(speed) <= 100:
                raise ValueError(
                    "filter speed must be between 10 and 100 percent")
            if not _finite(post_run) or not 0 <= float(post_run) <= 120:
                raise ValueError(
                    "filter post-run must be between 0 and 120 minutes")
            seen_tags.add(tag.casefold())
        profiles.append({
            "id": str(value.get("id", ""))[:80],
            "name": str(value.get("name", ""))[:80],
            "filter_enabled": enabled,
            "filter_tag": tag,
            "filter_fan": fan,
            "filter_speed_percent": float(speed),
            "filter_post_run_minutes": float(post_run),
        })
    return profiles


class ChamberFilterController:
    """Monitor print filenames and control only validated fan_generic objects."""

    def __init__(
            self, state_path, moonraker_url="http://127.0.0.1:7125",
            allow_commands=False, poll_interval=1.0, send_gcode=None,
            status_provider=None, wall_time=None):
        self.state_path = os.path.expanduser(state_path)
        self.moonraker_url = moonraker_url.rstrip("/")
        self.allow_commands = bool(allow_commands)
        self.poll_interval = float(poll_interval)
        self._send_gcode = send_gcode or self._moonraker_gcode
        self._status_provider = status_provider or self._moonraker_status
        self._wall_time = wall_time or time.time
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.profiles = []
        self.available_fans = []
        self.state = "idle"
        self.filename = None
        self.matched_profile = None
        self.active_fan = None
        self.active_speed = None
        self.post_run_until = None
        self.last_command = None
        self.last_error = None
        self.monitor_error = None
        self.command_count = 0
        self.last_command_attempt = 0.0
        self._load_state()

    def _moonraker_status(self):
        request = urllib.request.Request(
            self.moonraker_url
            + "/printer/objects/query?print_stats&configfile",
            headers={"Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=1.5) as response:
            payload = json.load(response)
        return payload["result"]["status"]

    def _moonraker_gcode(self, script):
        body = json.dumps({"script": script}).encode("utf-8")
        request = urllib.request.Request(
            self.moonraker_url + "/printer/gcode/script",
            data=body, method="POST",
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=2.0) as response:
            json.load(response)

    def _load_state(self):
        try:
            with open(self.state_path, encoding="utf-8") as handle:
                payload = json.load(handle)
            self.profiles = payload.get("profiles", [])
            runtime = payload.get("runtime") or {}
            active_fan = runtime.get("active_fan")
            self.active_fan = (
                active_fan
                if isinstance(active_fan, str)
                and FAN_NAME_RE.fullmatch(active_fan)
                else None)
            active_speed = runtime.get("active_speed")
            self.active_speed = (
                float(active_speed) if _finite(active_speed) else None)
            post_run_until = runtime.get("post_run_until")
            self.post_run_until = (
                float(post_run_until) if _finite(post_run_until) else None)
            self.matched_profile = runtime.get("matched_profile")
            if self.active_fan:
                self.state = "recovering"
        except (FileNotFoundError, OSError, ValueError):
            pass

    def _save_state(self):
        parent = os.path.dirname(self.state_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        temporary = self.state_path + ".tmp"
        payload = {
            "profiles": self.profiles,
            "runtime": {
                "active_fan": self.active_fan,
                "active_speed": self.active_speed,
                "post_run_until": self.post_run_until,
                "matched_profile": self.matched_profile,
            },
        }
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, self.state_path)

    @staticmethod
    def _fans_from_status(status):
        settings = (
            (status.get("configfile") or {}).get("settings") or {})
        return sorted(
            name.split(" ", 1)[1]
            for name in settings
            if name.startswith("fan_generic ") and " " in name)

    def update_profiles(self, values):
        status = self._status_provider()
        available_fans = self._fans_from_status(status)
        profiles = validated_profiles(values, available_fans)
        with self.lock:
            self.available_fans = available_fans
            self.profiles = profiles
            self._save_state()
        return self.status()

    def _matching_profile(self, filename):
        matches = [
            profile for profile in self.profiles
            if profile.get("filter_enabled")
            and profile.get("filter_tag", "").casefold()
            in filename.casefold()
        ]
        if not matches:
            return None
        return max(matches, key=lambda item: len(item["filter_tag"]))

    def _command(self, fan, speed):
        now = self._wall_time()
        if now - self.last_command_attempt < 5.0:
            return False
        self.last_command_attempt = now
        command = "SET_FAN_SPEED FAN=%s SPEED=%.3f" % (fan, speed)
        try:
            self._send_gcode(command)
            self.last_command = command
            self.command_count += 1
            self.last_error = None
            return True
        except Exception as exc:
            self.last_error = repr(exc)
            self.state = "error"
            return False

    def _activate(self, profile):
        fan = profile["filter_fan"]
        speed = profile["filter_speed_percent"] / 100.0
        if (not FAN_NAME_RE.fullmatch(fan)
                or fan not in self.available_fans
                or not _finite(speed)
                or not 0.1 <= speed <= 1.0):
            self.last_error = "configured chamber filter is unavailable"
            self.state = "error"
            return
        if (self.active_fan == fan
                and self.active_speed == speed
                and self.state == "active"):
            return
        self.matched_profile = {
            "id": profile["id"],
            "name": profile["name"],
            "filter_tag": profile["filter_tag"],
            "filter_fan": fan,
            "filter_speed_percent": profile["filter_speed_percent"],
            "filter_post_run_minutes":
                profile["filter_post_run_minutes"],
        }
        if not self.allow_commands:
            self.state = "matched_locked"
            return
        if self._command(fan, speed):
            self.active_fan = fan
            self.active_speed = speed
            self.post_run_until = None
            self.state = "active"
            self._save_state()

    def _begin_post_run(self):
        if not self.active_fan:
            return
        minutes = float(
            (self.matched_profile or {}).get(
                "filter_post_run_minutes", 20))
        self.post_run_until = self._wall_time() + minutes * 60.0
        self.state = "post_run"
        self._save_state()

    def _finish_post_run(self):
        if not self.active_fan:
            self.state = "idle"
            return
        if not self.allow_commands:
            self.state = "post_run_locked"
            return
        fan = self.active_fan
        if self._command(fan, 0.0):
            self.active_fan = None
            self.active_speed = None
            self.post_run_until = None
            self.matched_profile = None
            self.state = "idle"
            self._save_state()

    def step(self, status=None):
        try:
            status = status or self._status_provider()
            available_fans = self._fans_from_status(status)
            print_stats = status.get("print_stats") or {}
            print_state = print_stats.get("state")
            filename = os.path.basename(str(
                print_stats.get("filename") or ""))
            with self.lock:
                self.monitor_error = None
                self.available_fans = available_fans
                self.filename = filename or None
                if print_state in ACTIVE_PRINT_STATES:
                    profile = self._matching_profile(filename)
                    if profile:
                        self._activate(profile)
                    elif not self.active_fan:
                        self.matched_profile = None
                        self.state = "idle"
                elif self.active_fan and self.post_run_until is None:
                    self._begin_post_run()
                elif (self.active_fan
                      and self.post_run_until is not None
                      and self._wall_time() >= self.post_run_until):
                    self._finish_post_run()
                elif self.active_fan:
                    self.state = "post_run"
                elif not self.active_fan:
                    self.matched_profile = None
                    self.state = "error" if self.last_error else "idle"
                return self.status()
        except Exception as exc:
            with self.lock:
                self.monitor_error = repr(exc)
                if self.active_fan:
                    self.state = "monitor_warning"
                else:
                    self.state = "error"
                return self.status()

    def _run(self):
        while not self.stop_event.wait(self.poll_interval):
            self.step()

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self._run, name="autopa-chamber-filter", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(2.0)

    def status(self):
        with self.lock:
            remaining = (
                max(0.0, self.post_run_until - self._wall_time())
                if self.post_run_until is not None else 0.0)
            return {
                "state": self.state,
                "allowCommands": self.allow_commands,
                "availableFans": list(self.available_fans),
                "filename": self.filename,
                "matchedProfile": self.matched_profile,
                "activeFan": self.active_fan,
                "activeSpeedPercent": (
                    self.active_speed * 100.0
                    if self.active_speed is not None else None),
                "postRunSecondsRemaining": remaining,
                "configuredProfiles": sum(
                    1 for profile in self.profiles
                    if profile.get("filter_enabled")),
                "lastCommand": self.last_command,
                "lastError": self.last_error or self.monitor_error,
                "commandCount": self.command_count,
                "printerAction": (
                    "chamber_filter_only"
                    if self.active_fan else "none"),
            }

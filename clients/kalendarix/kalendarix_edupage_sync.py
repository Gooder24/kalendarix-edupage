#!/usr/bin/env python3
"""Mirror the EduPage timetable from the backend into Kalendarix as one calendar.

Kalendarix keeps every calendar in a single JSON file that it rewrites on each
change, and a desktop panel calendar may watch that same file. This script
replaces the timetable events of one calendar in it and leaves the rest untouched.

Standard library only: it runs from a systemd timer on the laptop.
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_URL = "http://127.0.0.1:8787"  # the backend on another machine: set KX_EDUPAGE_URL
DEFAULT_FILE = "~/.config/kalendarix/calendars.json"

# The calendar id and the uid suffix are already stored in existing calendars.json files (the
# project was called lifeOS): changing them would duplicate every lesson.
CALENDAR_ID = "lifeos-edupage"
DEFAULT_COLOR = "#a6e3a1"  # light green: school; subjects add their own colour
OURS = "@lifeos"  # uid suffix of the events this script owns


def kalendarix_time(iso: str) -> str:
    # Kalendarix stores Date.toISOString(): UTC with milliseconds.
    moment = datetime.fromisoformat(iso).astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def kalendarix_event(event: dict) -> dict:
    out = {
        "uid": event["uid"],
        "title": event["title"],
        "description": event["description"],
        "notes": event["description"],
        "location": event["location"],
        "start": kalendarix_time(event["start"]),
        "end": kalendarix_time(event["end"]),
        "allDay": event["all_day"],
        "rrule": None,
        "exdates": [],
        "alarmMinutes": "",  # no reminder: a school day would mean seven of them
    }
    if event.get("color"):
        # The subject's own colour, beside the calendar's. Kalendarix does not
        # draw it yet and drops the field when it saves; the next run restores it.
        out["color"] = event["color"]
    return out


def merge(data: dict, events: list[dict], name: str, color: str | None = None) -> bool:
    """Put the events into our calendar inside `data`. True when anything changed.

    The calendar's name, colour and visibility are the user's once it exists;
    `color` overrides the colour only when given.
    """
    calendars = data.setdefault("calendars", [])
    calendar = next((c for c in calendars if c.get("id") == CALENDAR_ID), None)
    changed = False
    if calendar is None:
        # customColor keeps it this green in every theme.
        calendar = {
            "id": CALENDAR_ID, "name": name, "color": DEFAULT_COLOR, "visible": True,
            "colorSlot": 1, "customColor": DEFAULT_COLOR, "events": [],
        }
        calendars.append(calendar)
        changed = True
    if color and calendar.get("customColor") != color:
        calendar["color"] = calendar["customColor"] = color
        changed = True

    current = calendar.get("events", [])
    # Only what came from the backend is replaced; events added by hand stay.
    kept = [e for e in current if not str(e.get("uid", "")).endswith(OURS)]
    updated = kept + [kalendarix_event(e) for e in events]
    if updated != current:
        calendar["events"] = updated
        changed = True
    return changed


def fetch_events(base_url: str, attempts: int) -> list[dict]:
    # Right after the laptop wakes the tailnet needs a moment: try a few times.
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(f"{base_url}/api/events", timeout=15) as response:
                return json.load(response)["events"]
        except OSError:
            if attempt == attempts - 1:
                raise
            time.sleep(5)
    raise AssertionError("unreachable")


def _version(stat: os.stat_result | None):
    return (stat.st_mtime_ns, stat.st_size) if stat else None


def write_if_unchanged(path: Path, before: os.stat_result | None, text: str) -> bool:
    """Replace the file atomically, unless someone else wrote it since we read it."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".calendars-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, before.st_mode & 0o777 if before else 0o644)
        try:
            now = path.stat()
        except FileNotFoundError:
            now = None
        if _version(now) != _version(before):
            return False  # Kalendarix saved in the meantime: start over from its version
        os.replace(tmp, path)
        return True
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=os.environ.get("KX_EDUPAGE_URL", DEFAULT_URL))
    parser.add_argument("--file", default=os.environ.get("KALENDARIX_FILE", DEFAULT_FILE))
    parser.add_argument("--name", default="EduPage rozvrh", help="name of the calendar when first created")
    parser.add_argument("--color", help="set the calendar's colour, also when it already exists")
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    args = parser.parse_args()
    path = Path(args.file).expanduser()

    try:
        events = fetch_events(args.url.rstrip("/"), args.attempts)
    except OSError as exc:
        # Normal away from the tailnet or while the backend is off: keep the last copy.
        print(f"EduPage timetable backend unreachable ({exc}); calendar left as it is")
        return 0

    for _ in range(3):
        try:
            before = path.stat()
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            before, data = None, {}
        # A half-written or foreign file raises here, and nothing gets written.

        if not merge(data, events, args.name, args.color):
            print(f"up to date: {len(events)} events")
            return 0
        if args.dry_run:
            print(f"would write {len(events)} events into calendar '{CALENDAR_ID}' in {path}")
            return 0

        backup = path.with_name(path.name + ".before-edupage")
        if before and not backup.exists():
            shutil.copy2(path, backup)  # one copy from before this script ever wrote
        path.parent.mkdir(parents=True, exist_ok=True)
        # Same layout as Kalendarix's JSON.stringify(data, null, 2).
        if write_if_unchanged(path, before, json.dumps(data, indent=2, ensure_ascii=False)):
            print(f"updated: {len(events)} events")
            return 0

    print("calendars.json kept changing while syncing; will retry on the next run", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

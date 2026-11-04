"""Render lessons as an iCalendar (RFC 5545) feed any calendar app can subscribe to."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from kalendarix_edupage.events import to_events

UTC_FORMAT = "%Y%m%dT%H%M%SZ"


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> str:
    """Fold a content line to the 75-octet limit without splitting a character."""
    raw = line.encode("utf-8")
    chunks = []
    while raw:
        cut = min(len(raw), 75 if not chunks else 74)  # continuation adds a space
        while cut < len(raw) and raw[cut] & 0xC0 == 0x80:
            cut -= 1
        chunks.append(raw[:cut].decode("utf-8"))
        raw = raw[cut:]
    return "\r\n ".join(chunks)


def _utc(moment: datetime) -> str:
    # Emitting UTC avoids shipping a VTIMEZONE block for the school's zone.
    return moment.astimezone(timezone.utc).strftime(UTC_FORMAT)


def _vevent(event: dict, stamp: str) -> list[str]:
    lines = ["BEGIN:VEVENT", f"UID:{event['uid']}", f"DTSTAMP:{stamp}"]
    if event["all_day"]:
        lines += [
            f"DTSTART;VALUE=DATE:{event['start']:%Y%m%d}",
            f"DTEND;VALUE=DATE:{event['end']:%Y%m%d}",
        ]
    else:
        lines += [f"DTSTART:{_utc(event['start'])}", f"DTEND:{_utc(event['end'])}"]
    lines.append(f"SUMMARY:{_escape(event['title'])}")
    if event["location"]:
        lines.append("LOCATION:" + _escape(event["location"]))
    if event["description"]:
        lines.append("DESCRIPTION:" + _escape(event["description"]))
    if event["cancelled"]:
        lines.append("STATUS:CANCELLED")
    lines.append("END:VEVENT")
    return lines


def build_calendar(lessons: list[dict], tz: ZoneInfo, now: datetime) -> str:
    stamp = _utc(now)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Kalendarix EduPage//SK",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:EduPage rozvrh",
    ]
    for event in to_events(lessons, tz):
        lines += _vevent(event, stamp)
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"

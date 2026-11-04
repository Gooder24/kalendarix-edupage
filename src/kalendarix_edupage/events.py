"""How lessons are presented in a calendar: shared by the ICS feed and /api/events."""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

# How a whole-day entry is stored (EduPage's 24:00 becomes 23:59).
ALL_DAY = ("00:00", "23:59")

# Periods of one block may be this far apart and still be one event: breaks,
# lunch included. Two lessons with another one between them are further apart.
MAX_GAP = timedelta(minutes=45)

# One colour per subject, handed out in order of first appearance. Kalendarix's
# own picker colours plus a few more; no greens, the calendar itself is green.
SUBJECT_COLORS = [
    "#ff3b30", "#ff9500", "#ffcc00", "#00c7be", "#30b0c7", "#007aff", "#5856d6",
    "#af52de", "#ff2d55", "#a2845e", "#64d2ff", "#e2c08d", "#bf8cff", "#ff7ab2",
]


def assign_colors(known: dict[str, str], lessons: list[dict]) -> dict[str, str]:
    """`known` plus a colour for every subject it does not have yet."""
    colors = dict(known)
    for lesson in lessons:
        subject = lesson["subject"]
        if subject and subject not in colors:
            colors[subject] = SUBJECT_COLORS[len(colors) % len(SUBJECT_COLORS)]
    return colors


def to_events(lessons: list[dict], tz: ZoneInfo, colors: dict[str, str] | None = None) -> list[dict]:
    """Calendar events for stored lessons, in the order given.

    Consecutive periods of the same thing (a practice day, a class trip, a
    double lesson) become one event that runs through the breaks.
    """
    blocks: list[dict] = []
    for lesson in lessons:
        block = _block(lesson, tz)
        if block is None:
            continue
        earlier = next((b for b in reversed(blocks) if _continues(b, block)), None)
        if earlier:
            earlier["end"] = block["end"]
            earlier["periods"] += block["periods"]
            earlier["topics"] += [t for t in block["topics"] if t not in earlier["topics"]]
        else:
            blocks.append(block)
    return [_event(block, colors or {}) for block in blocks]


def _block(lesson: dict, tz: ZoneInfo) -> dict | None:
    if not (lesson["start"] and lesson["end"]):
        return None  # nowhere to put it

    day = date.fromisoformat(lesson["date"])
    all_day = (lesson["start"], lesson["end"]) == ALL_DAY
    if all_day:
        start = datetime.combine(day, time.min, tz)
        end = datetime.combine(day + timedelta(days=1), time.min, tz)  # exclusive
    else:
        start = datetime.combine(day, time.fromisoformat(lesson["start"]), tz)
        end = datetime.combine(day, time.fromisoformat(lesson["end"]), tz)

    # Rows stored before substitutions were tracked have neither key.
    replaced = {change["field"]: change["old"] for change in lesson.get("changes") or []}
    subject = lesson["subject"] or next(iter(replaced.get("subject") or []), None)
    name = subject or lesson["topic"] or "Hodina"
    if lesson["cancelled"]:
        status, title = "cancelled", f"Odpadlo: {name}"
    elif replaced.get("teacher"):
        status, title = "substitution", f"Suplovanie: {name}"
    elif replaced:
        status, title = "changed", f"Zmena: {name}"
    else:
        status, title = ("event" if lesson["is_event"] else "lesson"), name

    return {
        # "@lifeos" is the project's old name, kept: calendars already hold events by this uid.
        "uid": f"{lesson['date']}-{lesson['position']}@lifeos",
        "title": title,
        "status": status,
        "subject": subject,
        "location": ", ".join(lesson["classrooms"]),
        "teachers": lesson["teachers"],
        "groups": lesson["groups"],
        "replaced": replaced,
        "notes": lesson.get("notes") or [],
        "online_link": lesson["online_link"],
        "start": start,
        "end": end,
        "all_day": all_day,
        "periods": [lesson["period"]] if lesson["period"] is not None else [],
        # A topic that already is the title (events without a subject) is not repeated.
        "topics": [lesson["topic"]] if lesson["topic"] and lesson["topic"] != name else [],
    }


_SAME = ("title", "status", "location", "teachers", "groups", "replaced", "notes")


def _continues(earlier: dict, block: dict) -> bool:
    return (
        not earlier["all_day"]
        and not block["all_day"]
        and all(earlier[key] == block[key] for key in _SAME)
        and timedelta(0) <= block["start"] - earlier["end"] <= MAX_GAP
    )


def _event(block: dict, colors: dict[str, str]) -> dict:
    replaced = block["replaced"]
    details = []
    if block["teachers"]:
        line = "Učiteľ: " + ", ".join(block["teachers"])
        if replaced.get("teacher"):
            line += f" (namiesto: {', '.join(replaced['teacher'])})"
        details.append(line)
    if replaced.get("classroom"):
        details.append(
            f"Učebňa: {block['location'] or '?'} (namiesto: {', '.join(replaced['classroom'])})"
        )
    if replaced.get("subject") and block["status"] != "cancelled":
        details.append("Namiesto predmetu: " + ", ".join(replaced["subject"]))
    # "Odpadlo" is already the title of a cancelled lesson.
    details += [n for n in block["notes"] if not (block["status"] == "cancelled" and n == "Odpadlo")]
    # For seminar groups EduPage names the group in a remark ("Skupina: Seminár 3")
    # and keeps only an internal key ("seminargroup:3") in the group list.
    if block["groups"] and not any(note.startswith("Skupina:") for note in block["notes"]):
        details.append("Skupina: " + ", ".join(block["groups"]))
    if block["periods"]:
        first, last = block["periods"][0], block["periods"][-1]
        details.append(f"Hodina: {first}." if first == last else f"Hodiny: {first}.–{last}.")
    if block["topics"]:
        details.append("Téma: " + "; ".join(block["topics"]))
    if block["online_link"]:
        details.append("Online: " + block["online_link"])

    return {
        "uid": block["uid"],
        "title": block["title"],
        "location": block["location"],
        "description": "\n".join(details),
        "start": block["start"],
        "end": block["end"],
        "all_day": block["all_day"],
        # lesson | event | substitution | changed | cancelled
        "status": block["status"],
        "cancelled": block["status"] == "cancelled",
        "subject": block["subject"],
        "color": colors.get(block["subject"]),
    }

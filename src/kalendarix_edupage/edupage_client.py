"""Thin wrapper around edupage-api: login with session reuse, timetable fetch."""

import json
import os
from dataclasses import dataclass
from datetime import date

from edupage_api import Edupage
from edupage_api.exceptions import (
    BadCredentialsException,
    CaptchaException,
    MissingDataException,
)
from edupage_api.timetables import Timetables
from edupage_api.twofactor import TwoFactorLogin

from kalendarix_edupage.config import Settings

SESSION_FILE = "edupage_session.json"


class EdupageLoginError(Exception):
    """Login failed in a way that retrying will not fix. The message is user-facing."""


def fresh_login(settings: Settings) -> tuple[Edupage, TwoFactorLogin | None]:
    """Log in with username and password.

    Returns the second-factor handle when the account has 2FA enabled; the
    login is only complete once that is finished.
    """
    if not settings.edupage_configured:
        raise EdupageLoginError(
            "Chýbajú prihlasovacie údaje – vyplň EDUPAGE_SUBDOMAIN, "
            "EDUPAGE_USERNAME a EDUPAGE_PASSWORD v súbore .env."
        )

    edupage = Edupage(request_timeout=15)
    try:
        two_factor = edupage.login(
            settings.edupage_username,
            settings.edupage_password,
            settings.edupage_subdomain,
        )
    except CaptchaException as exc:
        raise EdupageLoginError(
            "EduPage vyžaduje captcha (príliš veľa prihlásení). Prihlás sa raz "
            "ručne v prehliadači a skús to znova o chvíľu."
        ) from exc
    except BadCredentialsException as exc:
        raise EdupageLoginError(
            f"EduPage odmietol prihlásenie – skontroluj subdoménu, meno a heslo. ({exc})"
        ) from exc
    return edupage, two_factor


def save_session(settings: Settings, edupage: Edupage) -> bool:
    """Persist the session cookie so restarts do not trigger a new login."""
    session_id = edupage.session.cookies.get(
        "PHPSESSID", domain=f"{edupage.subdomain}.edupage.org"
    )
    if not session_id:
        return False

    settings.kx_data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = settings.kx_data_dir / SESSION_FILE
    payload = {
        "session_id": session_id,
        "subdomain": edupage.subdomain,
        "username": settings.edupage_username,
    }
    # The cookie is as good as the password while it lives: owner-only.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(payload, f)
    return True


def restore_session(settings: Settings) -> Edupage | None:
    """Return a logged-in Edupage from the saved session, or None if unusable."""
    try:
        saved = json.loads((settings.kx_data_dir / SESSION_FILE).read_text())
    except (FileNotFoundError, ValueError):
        return None

    if saved.get("username") != settings.edupage_username:
        return None

    try:
        return Edupage.from_session_id(
            saved["session_id"], saved["subdomain"], saved["username"]
        )
    except (BadCredentialsException, KeyError):
        return None  # expired or malformed, fall back to a password login


def connect(settings: Settings) -> Edupage:
    """Logged-in Edupage for unattended use: saved session first, password second."""
    edupage = restore_session(settings)
    if edupage is not None:
        return edupage

    edupage, two_factor = fresh_login(settings)
    if two_factor is not None:
        raise EdupageLoginError(
            "Účet má zapnuté dvojfaktorové overenie. Spusti v termináli "
            "`kalendarix-edupage verify-login` a potvrď prihlásenie; backend potom použije "
            "uloženú reláciu."
        )
    save_session(settings, edupage)
    return edupage


@dataclass(frozen=True)
class Names:
    """Names for the ids a day plan uses, read once per sync from the login data."""

    subjects: dict[str, tuple[str, str]]  # id -> (name, short)
    teachers: dict[str, str]
    classrooms: dict[str, str]
    classes: dict[str, str]
    periods: dict[int, tuple[str, str]]  # period -> (start, end)


def load_names(edupage: Edupage) -> Names:
    return Names(
        subjects={str(s.subject_id): (s.name, s.short) for s in edupage.get_subjects() or []},
        teachers={str(t.person_id): t.name for t in edupage.get_teachers() or []},
        classrooms={str(c.classroom_id): c.short or c.name for c in edupage.get_classrooms() or []},
        classes={str(c.class_id): c.short or c.name for c in edupage.get_classes() or []},
        periods={
            int(bell["id"]): (bell["starttime"], bell["endtime"])
            for bell in edupage.data.get("zvonenia") or []
            if str(bell.get("id", "")).isdigit()
        },
    )


def fetch_day(edupage: Edupage, day: date, names: Names | None = None) -> list[dict]:
    """Fetch one day of the logged-in user's timetable as plain dicts."""
    names = names or load_names(edupage)
    try:
        plan = _raw_plan(edupage, day)
    except MissingDataException as exc:
        # The library raises this without a message when EduPage has no plan
        # for the date (holidays). With a message it is a real problem, e.g.
        # a parent account without a selected child.
        if exc.args:
            raise
        return []
    lessons = [lesson for item in plan if (lesson := _parse_item(day, item, names))]
    return _merge_duplicates(lessons)


def _raw_plan(edupage: Edupage, day: date) -> list[dict]:
    # The library's own parser drops what a substitution replaced and the
    # "Odpadlo" rows, so its raw day plan is read instead. This is a private
    # method: one more reason the dependency is pinned to an exact version.
    return Timetables(edupage)._Timetables__get_date_plan(day)


_COLUMNS = {
    "subjectid": "subject",
    "teacherids": "teacher",
    "classroomids": "classroom",
    "classids": "class",
}


def _named(column: str, ids, names: Names) -> list[str]:
    table = {
        "subjectid": {key: name for key, (name, _short) in names.subjects.items()},
        "teacherids": names.teachers,
        "classroomids": names.classrooms,
        "classids": names.classes,
    }.get(column, {})
    ids = ids if isinstance(ids, list) else [ids]
    return [table[str(i)] for i in ids if str(i) in table]


def _changes(item: dict, names: Names) -> list[dict]:
    """What a substitution replaced, e.g. [{"field": "teacher", "old": ["Ján Novák"]}]."""
    carriers = [part.get("item") for part in item.get("header") or []]
    carriers += [
        text.get("item") for info in item.get("infos") or [] for text in info.get("texts") or []
    ]
    found = []
    for carrier in carriers:
        for change in (carrier or {}).get("changes") or []:
            column = change.get("column")
            if not column:
                continue
            entry = {
                "field": _COLUMNS.get(column, column),
                "old": _named(column, change.get("old"), names),
            }
            if entry not in found:
                found.append(entry)
    return found


def _parse_item(day: date, item: dict, names: Names) -> dict | None:
    header = item.get("header") or []
    # As in the library: bare period rows and "add a lesson" prompts are not lessons.
    if "header" in item and (not header or header[0].get("cmd") == "addlesson_t"):
        return None

    flags = item.get("flags") if isinstance(item.get("flags"), dict) else {}
    plan = flags.get("dp0") if isinstance(flags.get("dp0"), dict) else {}
    event = flags.get("event") if isinstance(flags.get("event"), dict) else {}
    kind = item.get("type")
    period = int(raw) if (raw := str(item.get("uniperiod") or "")).isdigit() else None

    start, end = item.get("starttime"), item.get("endtime")
    if not (start and end):
        # A cancelled lesson comes without times; the bell schedule has them.
        start, end = names.periods.get(period, (None, None))

    # A cancelled lesson keeps its subject only in the header.
    subject_id = item.get("subjectid") or next(
        (part["item"]["subjectid"] for part in header if (part.get("item") or {}).get("subjectid")),
        None,
    )
    subject = names.subjects.get(str(subject_id))
    is_event = kind in ("event", "out") or bool(item.get("main"))

    topic = plan.get("note_wd") or event.get("name")
    if not topic and is_event and not subject and isinstance(item.get("name"), str):
        topic = item["name"].strip()  # some school events carry their title here

    return {
        "date": day.isoformat(),
        "period": period,
        "start": _clock(start),
        "end": _clock(end),
        "subject": subject[0] if subject else None,
        "subject_short": subject[1] if subject else None,
        "teachers": _named("teacherids", item.get("teacherids") or [], names),
        "classrooms": _named("classroomids", item.get("classroomids") or [], names),
        "classes": _named("classids", item.get("classids") or [], names),
        "groups": [group for group in item.get("groupnames") or [] if group],
        "topic": topic or None,
        "online_link": item.get("ol_url"),
        "cancelled": bool(item.get("removed")) or kind in ("absent", ""),
        "is_event": is_event,
        "changes": _changes(item, names),
        # Free remarks such as "Odpadlo"; the curriculum ("wd") is the topic above.
        "notes": [
            remark
            for info in item.get("infos") or []
            if info.get("type") != "wd"
            for text in info.get("texts") or []
            if not text.get("item") and (remark := (text.get("text") or "").strip())
        ],
    }


def _clock(value: str | None) -> str | None:
    # EduPage ends a whole day at 24:00, which is not a time of day.
    return "23:59" if value == "24:00" else (value or None)


def _merge_duplicates(lessons: list[dict]) -> list[dict]:
    """Collapse entries that differ only in their class list.

    EduPage keeps one record per audience (say one for two classes together and
    one for a single class), so a student would see the same lesson twice.
    """
    merged: dict[str, dict] = {}
    for lesson in lessons:
        key = json.dumps(
            {k: v for k, v in lesson.items() if k != "classes"}, sort_keys=True
        )
        kept = merged.setdefault(key, lesson)
        if kept is not lesson:
            kept["classes"] += [c for c in lesson["classes"] if c not in kept["classes"]]
    return list(merged.values())

import stat
from datetime import date

import pytest
import requests
from edupage_api import Edupage
from edupage_api.classes import Class
from edupage_api.classrooms import Classroom
from edupage_api.exceptions import BadCredentialsException, MissingDataException
from edupage_api.people import EduTeacher
from edupage_api.subjects import Subject

from kalendarix_edupage import edupage_client

DAY = date(2026, 10, 12)

NAMES = edupage_client.Names(
    subjects={"7": ("Slovenský jazyk", "SJL"), "-7": ("Matematika", "MAT")},
    teachers={"11": "Mária Kováčová", "12": "Ján Novák"},
    classrooms={"5": "12", "6": "31"},
    classes={"1": "III. A", "2": "III. B"},
    periods={6: ("13:00", "13:45"), 7: ("13:50", "14:35")},
)

# The shapes below are EduPage's own, as seen in a real day plan (2026-10).
LESSON = {
    "uniperiod": "3", "type": "lesson", "period": "3", "starttime": "09:45", "endtime": "10:30",
    "header": [{"item": {"subjectid": "7", "changes": [], "jeSkd": None}},
               {"icon": "/global/pics/ui/videocall_16.svg", "cmd": "onlinelesson"}],
    "infos": [{"type": "", "texts": [{"text": "Učiteľ: ", "item": {"teacherids": ["11"]}}]},
              {"type": "", "texts": [{"text": "Učebňa: ", "item": {"classroomids": ["5"], "changes": []}}]},
              {"type": "wd", "texts": [{"text": "Učivo: Vybrané slová"}]}],
    "flags": {"dp0": {"type": "card", "note_wd": "Vybrané slová"}},
    "subjectid": "7", "classids": ["1"], "teacherids": ["11"], "classroomids": ["5"],
    "groupnames": ["1. skupina", ""],
}
CANCELLED = {
    "uniperiod": "6", "type": "", "period": "6", "starttime": "", "endtime": "", "periodorbreak": "06P",
    "header": [{"item": {"subjectid": "-7", "changes": [{"column": "subjectid", "old": "-7"}]}}],
    "infos": [{"texts": [{"text": "Odpadlo"}]}],
    "flags": [], "classids": [], "teacherids": [], "classroomids": [], "groupnames": [],
}
CLASS_EVENT = {
    "uniperiod": "1", "type": "event", "period": "1", "starttime": "08:00", "endtime": "08:45",
    "header": [{"icon": "/global/pics/ui/events_16.svg", "text": "Udalosť s triednym učiteľom: Triednické práce"}],
    "infos": [{"type": "", "texts": [{"text": "Učiteľ: ", "item": {"teacherids": ["12"]}}]}],
    "flags": {"dp0": {"type": "event", "eventid": "2026-10-14:DC84"}, "event": {"name": "Triednické práce"}},
    "subjectid": "", "classids": ["1"], "teacherids": ["12"], "classroomids": [], "groupnames": [""],
}
WHOLE_DAY = {
    "uniperiod": "ad", "type": "event", "allday": 1, "starttime": "00:00", "endtime": "24:00",
    "header": [{"icon": "/global/pics/ui/events_16.svg", "text": "Vyučovacie voľno: Vyučovacie voľno"}],
    "infos": [], "flags": {"dp0": {"type": "event"}, "event": {"name": "Vyučovacie voľno"}},
    "classids": [], "teacherids": [], "classroomids": [], "groupnames": [""],
}
EMPTY_PERIOD = {"type": "period", "uniperiod": "8", "period": "8", "periodorbreak": "08P", "header": [],
                "flags": [], "classids": [], "groupnames": [], "classroomids": []}


@pytest.fixture
def plan(monkeypatch):
    def fetch(*items):
        monkeypatch.setattr(edupage_client, "_raw_plan", lambda edupage, day: list(items))
        return edupage_client.fetch_day(object(), DAY, NAMES)

    return fetch


def test_lesson_is_flattened_to_names(plan):
    assert plan(LESSON) == [{
        "date": "2026-10-12",
        "period": 3,
        "start": "09:45",
        "end": "10:30",
        "subject": "Slovenský jazyk",
        "subject_short": "SJL",
        "teachers": ["Mária Kováčová"],
        "classrooms": ["12"],
        "classes": ["III. A"],
        "groups": ["1. skupina"],
        "topic": "Vybrané slová",
        "online_link": None,
        "cancelled": False,
        "is_event": False,
        "changes": [],
        "notes": [],
    }]


def test_cancelled_lesson_keeps_its_subject_and_gets_the_bell_times(plan):
    [gone] = plan(CANCELLED)

    assert gone["cancelled"] is True and gone["subject"] == "Matematika"
    assert (gone["period"], gone["start"], gone["end"]) == (6, "13:00", "13:45")
    assert gone["changes"] == [{"field": "subject", "old": ["Matematika"]}]
    assert gone["notes"] == ["Odpadlo"]


def test_school_event_is_named_by_its_event_and_empty_periods_are_skipped(plan):
    event, whole_day = plan(CLASS_EVENT, WHOLE_DAY, EMPTY_PERIOD)

    assert event["is_event"] and event["subject"] is None and event["topic"] == "Triednické práce"
    assert event["teachers"] == ["Ján Novák"] and event["cancelled"] is False
    assert (whole_day["start"], whole_day["end"], whole_day["period"]) == ("00:00", "23:59", None)


def test_substitution_records_who_was_replaced(plan):
    # Assumed from the cancelled row: the same `changes` list on the teacher line.
    substituted = LESSON | {
        "teacherids": ["12"],
        "infos": [{"type": "", "texts": [
            {"text": "Učiteľ: ", "item": {"teacherids": ["12"], "changes": [{"column": "teacherids", "old": ["11"]}]}},
        ]}],
    }

    [lesson] = plan(substituted)

    assert lesson["teachers"] == ["Ján Novák"]
    assert lesson["changes"] == [{"field": "teacher", "old": ["Mária Kováčová"]}]


def test_same_lesson_listed_per_audience_is_shown_once(plan):
    both_classes = LESSON | {"classids": ["1", "2"]}

    result = plan(LESSON, both_classes, LESSON | {"uniperiod": "4", "starttime": "10:50", "endtime": "11:35"})

    assert [(lesson["period"], lesson["classes"]) for lesson in result] == [
        (3, ["III. A", "III. B"]),
        (4, ["III. A"]),
    ]


def test_day_without_plan_is_empty_but_real_problems_surface(monkeypatch):
    def raising(error):
        def raw_plan(edupage, day):
            raise error
        monkeypatch.setattr(edupage_client, "_raw_plan", raw_plan)

    raising(MissingDataException())
    assert edupage_client.fetch_day(object(), DAY, NAMES) == []

    raising(MissingDataException("The server didn't return a timetable for this account."))
    with pytest.raises(MissingDataException):
        edupage_client.fetch_day(object(), DAY, NAMES)


def test_names_come_from_the_librarys_lists_and_the_bell_schedule():
    class LoggedIn:
        data = {"zvonenia": [{"id": "1", "starttime": "08:00", "endtime": "08:45"},
                             {"id": "x", "starttime": "", "endtime": ""}]}

        def get_subjects(self):
            return [Subject(-7, "Matematika", "MAT")]

        def get_teachers(self):
            return [EduTeacher(11, "Mária Kováčová", None, None, "12", None)]

        def get_classrooms(self):
            return [Classroom(5, "Učebňa 12", "12"), Classroom(6, "Telocvičňa", "")]

        def get_classes(self):
            return [Class(1, "III. A", "III. A", None, None, 3)]

    names = edupage_client.load_names(LoggedIn())

    assert names.subjects == {"-7": ("Matematika", "MAT")}
    assert names.teachers == {"11": "Mária Kováčová"}
    assert names.classrooms == {"5": "12", "6": "Telocvičňa"}
    assert names.classes == {"1": "III. A"}
    assert names.periods == {1: ("08:00", "08:45")}


def test_session_is_saved_owner_only_and_restored(settings, monkeypatch):
    edupage = Edupage()
    edupage.subdomain = "skola"
    edupage.session.cookies.set("PHPSESSID", "abc123", domain="skola.edupage.org")
    restored_with = []
    monkeypatch.setattr(
        Edupage, "from_session_id", lambda *args: restored_with.append(args) or "client"
    )

    assert edupage_client.save_session(settings, edupage) is True
    path = settings.kx_data_dir / edupage_client.SESSION_FILE
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert edupage_client.restore_session(settings) == "client"
    assert restored_with == [("abc123", "skola", "ziak")]


def test_expired_session_falls_back_to_password_login(settings, monkeypatch):
    edupage = Edupage()
    edupage.subdomain = "skola"
    edupage.session.cookies.set("PHPSESSID", "expired", domain="skola.edupage.org")
    edupage_client.save_session(settings, edupage)

    def expired(*args):
        raise BadCredentialsException("EduPage did not return login data")

    monkeypatch.setattr(Edupage, "from_session_id", expired)
    monkeypatch.setattr(edupage_client, "fresh_login", lambda settings: (edupage, None))

    assert edupage_client.restore_session(settings) is None
    assert edupage_client.connect(settings) is edupage


def test_missing_credentials_are_reported_without_contacting_edupage(settings, monkeypatch):
    settings.edupage_password = ""

    def no_network(*args, **kwargs):
        raise AssertionError("must not reach the network")

    monkeypatch.setattr(requests.Session, "request", no_network)

    with pytest.raises(edupage_client.EdupageLoginError, match="EDUPAGE_PASSWORD"):
        edupage_client.connect(settings)

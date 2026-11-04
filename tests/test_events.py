from datetime import datetime
from zoneinfo import ZoneInfo

from conftest import make_lesson

from kalendarix_edupage.events import assign_colors, to_events

TZ = ZoneInfo("Europe/Bratislava")
BELLS = {1: ("08:00", "08:45"), 2: ("08:50", "09:35"), 3: ("09:45", "10:30"), 4: ("10:50", "11:35"),
         5: ("11:45", "12:30"), 6: ("13:00", "13:45"), 7: ("13:50", "14:35")}


def lesson(period, **overrides) -> dict:
    start, end = BELLS[period]
    return make_lesson(period=period, start=start, end=end, **overrides)


def events(*lessons, colors=None) -> list[dict]:
    return to_events([l | {"position": i} for i, l in enumerate(lessons)], TZ, colors)


def span(event) -> str:
    return f"{event['start']:%H:%M}-{event['end']:%H:%M}"


def test_practice_day_is_one_event_through_breaks_and_lunch():
    [practice] = events(*[lesson(p, subject="Odborná prax", teachers=[], classrooms=[]) for p in range(1, 8)])

    assert practice["title"] == "Odborná prax" and span(practice) == "08:00-14:35"
    assert practice["description"] == "Hodiny: 1.–7."
    assert practice["uid"] == "2026-10-12-0@lifeos"


def test_school_event_spread_over_periods_is_one_event_named_once():
    name = "Triednické práce - príprava rekonštruovaných priestorov školy"
    [work] = events(*[lesson(p, subject=None, topic=name, is_event=True, classrooms=[]) for p in range(1, 6)])

    assert work["title"] == name and work["status"] == "event" and span(work) == "08:00-12:30"
    assert work["description"] == "Učiteľ: Ján Novák\nHodiny: 1.–5."


def test_only_consecutive_periods_of_the_same_lesson_join():
    maths = dict(subject="Matematika")
    result = events(lesson(1, **maths), lesson(2, subject="Fyzika"), lesson(3, **maths), lesson(4, **maths),
                    lesson(5, subject="Matematika", teachers=["Iná Učiteľka"]))

    assert [(e["title"], span(e)) for e in result] == [
        ("Matematika", "08:00-08:45"), ("Fyzika", "08:50-09:35"),
        ("Matematika", "09:45-11:35"), ("Matematika", "11:45-12:30"),
    ]


def test_parallel_groups_listed_alternately_still_join_with_their_own():
    a, b = dict(subject="Anglický jazyk", groups=["1. skupina"]), dict(subject="Nemecký jazyk", groups=["2. skupina"])

    result = events(lesson(1, **a), lesson(1, **b), lesson(2, **a), lesson(2, **b))

    assert [(e["title"], span(e)) for e in result] == [
        ("Anglický jazyk", "08:00-09:35"), ("Nemecký jazyk", "08:00-09:35"),
    ]


def test_topics_of_joined_lessons_are_listed_once_each():
    [block] = events(lesson(1, topic="Číselníky"), lesson(2, topic="Číselníky"), lesson(3, topic="Faktúry"))

    assert block["description"] == "Učiteľ: Ján Novák\nHodiny: 1.–3.\nTéma: Číselníky; Faktúry"


def test_group_is_named_once_and_in_edupages_readable_form():
    [plain] = events(lesson(1, groups=["1. skupina"]))
    [seminar] = events(lesson(1, groups=["seminargroup:3"], notes=["Skupina: Seminár 3"]))

    assert plain["description"] == "Učiteľ: Ján Novák\nSkupina: 1. skupina\nHodina: 1."
    assert seminar["description"] == "Učiteľ: Ján Novák\nSkupina: Seminár 3\nHodina: 1."


def test_cancelled_lessons_say_so_and_join():
    dropped = dict(subject="Matematika", teachers=[], classrooms=[], cancelled=True, notes=["Odpadlo"],
                   changes=[{"field": "subject", "old": ["Matematika"]}])

    [gone] = events(lesson(6, **dropped), lesson(7, **dropped))

    assert gone["title"] == "Odpadlo: Matematika" and span(gone) == "13:00-14:35"
    assert gone["status"] == "cancelled" and gone["cancelled"] is True
    assert gone["description"] == "Hodiny: 6.–7."


def test_substitution_names_who_teaches_instead_of_whom():
    [sub] = events(lesson(2, teachers=["Eva Malá"], changes=[{"field": "teacher", "old": ["Ján Novák"]}]))

    assert sub["title"] == "Suplovanie: Matematika" and sub["status"] == "substitution"
    assert sub["description"] == "Učiteľ: Eva Malá (namiesto: Ján Novák)\nHodina: 2."


def test_other_changes_show_what_was_there_before():
    [moved] = events(lesson(2, classrooms=["12"], changes=[{"field": "classroom", "old": ["204"]}]))
    [swapped] = events(lesson(3, subject="Fyzika", changes=[{"field": "subject", "old": ["Matematika"]}]))

    assert moved["title"] == "Zmena: Matematika" and "Učebňa: 12 (namiesto: 204)" in moved["description"]
    assert swapped["title"] == "Zmena: Fyzika" and "Namiesto predmetu: Matematika" in swapped["description"]


def test_normal_lesson_and_its_substituted_neighbour_stay_apart():
    result = events(lesson(1), lesson(2, teachers=["Eva Malá"], changes=[{"field": "teacher", "old": ["Ján Novák"]}]))

    assert [e["title"] for e in result] == ["Matematika", "Suplovanie: Matematika"]


def test_whole_day_entry_stays_whole_day_and_alone():
    holiday = make_lesson(subject=None, topic="Vyučovacie voľno", start="00:00", end="23:59", period=None,
                          teachers=[], classrooms=[], is_event=True)

    whole, first = events(holiday, lesson(1))

    assert whole["all_day"] and whole["start"] == datetime(2026, 10, 12, tzinfo=TZ)
    assert whole["end"] == datetime(2026, 10, 13, tzinfo=TZ) and whole["description"] == ""
    assert first["all_day"] is False


def test_event_carries_its_subjects_colour():
    colors = assign_colors({}, [make_lesson(subject="Matematika"), make_lesson(subject="Fyzika")])

    maths, trip = events(lesson(1), lesson(3, subject=None, topic="Výlet", is_event=True), colors=colors)

    assert maths["color"] == colors["Matematika"] != colors["Fyzika"]
    assert trip["color"] is None and trip["subject"] is None


def test_rows_stored_before_changes_were_tracked_still_render():
    old_row = lesson(1)
    del old_row["changes"], old_row["notes"]

    assert events(old_row)[0]["title"] == "Matematika"

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from conftest import make_lesson

from kalendarix_edupage.ics import build_calendar

TZ = ZoneInfo("Europe/Bratislava")
NOW = datetime(2026, 10, 12, 6, 0, tzinfo=timezone.utc)


def render(*lessons) -> str:
    numbered = [lesson | {"position": i} for i, lesson in enumerate(lessons)]
    return build_calendar(numbered, TZ, NOW)


def unfolded(calendar: str) -> list[str]:
    return calendar.replace("\r\n ", "").split("\r\n")


def test_lesson_becomes_event_with_teacher_and_room():
    lines = unfolded(render(make_lesson()))

    assert "SUMMARY:Matematika" in lines
    assert "LOCATION:204" in lines
    assert "DESCRIPTION:Učiteľ: Ján Novák\\nHodina: 1." in lines
    assert "UID:2026-10-12-0@lifeos" in lines


def test_times_are_converted_to_utc_across_dst_change():
    summer = make_lesson(date="2026-10-23")  # CEST, UTC+2
    winter = make_lesson(date="2026-10-26")  # CET, UTC+1
    lines = unfolded(render(summer, winter))

    assert "DTSTART:20261023T060000Z" in lines
    assert "DTSTART:20261026T070000Z" in lines


def test_cancelled_lesson_is_marked():
    lines = unfolded(render(make_lesson(cancelled=True)))

    assert "SUMMARY:Odpadlo: Matematika" in lines
    assert "STATUS:CANCELLED" in lines


def test_event_without_subject_uses_its_topic_as_title():
    lines = unfolded(render(make_lesson(subject=None, topic="Účelové cvičenie")))

    assert "SUMMARY:Účelové cvičenie" in lines


def test_special_characters_are_escaped():
    lesson = make_lesson(subject="Dejepis; geografia, občianska", topic="a\nb")
    lines = unfolded(render(lesson))

    assert "SUMMARY:Dejepis\\; geografia\\, občianska" in lines
    assert "DESCRIPTION:Učiteľ: Ján Novák\\nHodina: 1.\\nTéma: a\\nb" in lines


def test_long_lines_fold_at_75_octets_without_breaking_characters():
    subject = " ".join(["Ťažká štátnicová skúška"] * 8)
    calendar = render(make_lesson(subject=subject))

    for line in calendar.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75
    assert f"SUMMARY:{subject}" in unfolded(calendar)


def test_untimed_entries_are_skipped():
    calendar = render(make_lesson(start=None, end=None))

    assert "BEGIN:VEVENT" not in calendar


def test_whole_day_entry_becomes_all_day_event():
    holiday = make_lesson(subject=None, topic="Vyučovacie voľno", start="00:00", end="23:59")
    lines = unfolded(render(holiday))

    assert "DTSTART;VALUE=DATE:20261012" in lines
    assert "DTEND;VALUE=DATE:20261013" in lines
    assert "SUMMARY:Vyučovacie voľno" in lines

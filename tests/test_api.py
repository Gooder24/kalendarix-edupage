from datetime import date, datetime, time, timedelta

import pytest
from conftest import make_lesson
from fastapi.testclient import TestClient

from kalendarix_edupage.api import create_app
from kalendarix_edupage.store import Store


@pytest.fixture
def client(settings):
    # No credentials: the app must not start syncing against EduPage in tests.
    settings.edupage_password = ""
    store = Store(settings.kx_data_dir)
    store.replace_day(date(2026, 10, 12), [make_lesson(), make_lesson(period=2)])
    store.replace_day(date(2026, 10, 13), [make_lesson(date="2026-10-13")])
    with TestClient(create_app(settings)) as client:
        yield client


def test_health_reports_missing_credentials(client):
    body = client.get("/health").json()

    assert body["status"] == "ok"
    assert body["edupage_configured"] is False
    assert body["last_sync"] is None


def test_timetable_returns_requested_range(client):
    body = client.get("/api/timetable", params={"from": "2026-10-12", "to": "2026-10-12"}).json()

    assert [lesson["period"] for lesson in body["lessons"]] == [1, 2]
    assert body["lessons"][0]["teachers"] == ["Ján Novák"]


def test_timetable_defaults_to_a_week_from_the_start_date(client):
    body = client.get("/api/timetable", params={"from": "2026-10-07"}).json()

    assert body["to"] == "2026-10-13"
    assert len(body["lessons"]) == 3


def test_token_is_required_once_configured(settings):
    settings.edupage_password = ""
    settings.kx_token = "tajny-token"
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/timetable").status_code == 401
        assert client.get("/calendar.ics", params={"token": "zle"}).status_code == 401
        assert client.get("/calendar.ics", params={"token": "tajny-token"}).status_code == 200
        ok = client.get("/api/timetable", headers={"Authorization": "Bearer tajny-token"})
        assert ok.status_code == 200


def test_calendar_feed_is_served_as_ics(settings):
    settings.edupage_password = ""
    with TestClient(create_app(settings)) as client:
        response = client.get("/calendar.ics")

    assert response.headers["content-type"] == "text/calendar; charset=utf-8"
    assert response.text.startswith("BEGIN:VCALENDAR\r\n")


def test_events_are_ready_made_for_a_calendar(settings):
    settings.edupage_password = ""
    today = datetime.now(settings.tz).date()
    lesson = make_lesson(date=today.isoformat())
    holiday = make_lesson(date=today.isoformat(), subject=None, topic="Voľno",
                          start="00:00", end="23:59", teachers=[], classrooms=[])
    Store(settings.kx_data_dir).replace_day(today, [lesson, holiday])
    with TestClient(create_app(settings)) as client:
        timed, whole_day = client.get("/api/events").json()["events"]

    assert timed["title"] == "Matematika" and timed["location"] == "204"
    assert timed["description"] == "Učiteľ: Ján Novák\nHodina: 1." and timed["status"] == "lesson"
    assert datetime.fromisoformat(timed["start"]) == datetime.combine(today, time(8, 0), settings.tz)
    assert whole_day["all_day"] is True and whole_day["title"] == "Voľno"
    assert datetime.fromisoformat(whole_day["end"]) - datetime.fromisoformat(whole_day["start"]) == timedelta(days=1)

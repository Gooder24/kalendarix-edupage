import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "clients/kalendarix/kalendarix_edupage_sync.py"
spec = importlib.util.spec_from_file_location("kalendarix_edupage_sync", SCRIPT)
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


def feed_event(uid="2026-10-12-0@lifeos", title="Matematika", **overrides) -> dict:
    event = {
        "uid": uid, "title": title, "location": "204", "description": "Učiteľ: Ján Novák",
        "start": "2026-10-12T08:00:00+02:00", "end": "2026-10-12T08:45:00+02:00",
        "all_day": False, "cancelled": False,
    }
    return event | overrides


def merged(data, events):
    changed = client.merge(data, events, "EduPage rozvrh")
    return changed, next(c for c in data["calendars"] if c["id"] == client.CALENDAR_ID)


def test_first_run_adds_one_calendar_and_leaves_the_others_alone():
    family = {"id": "kx-1", "name": "Rodinné", "events": [{"uid": "a", "title": "Oslava"}]}
    data = {"calendars": [json.loads(json.dumps(family))]}

    changed, calendar = merged(data, [feed_event()])

    assert changed and data["calendars"][0] == family
    assert calendar["name"] == "EduPage rozvrh" and calendar["customColor"] == client.DEFAULT_COLOR
    assert calendar["events"] == [{
        "uid": "2026-10-12-0@lifeos", "title": "Matematika", "description": "Učiteľ: Ján Novák",
        "notes": "Učiteľ: Ján Novák", "location": "204",
        "start": "2026-10-12T06:00:00.000Z", "end": "2026-10-12T06:45:00.000Z",
        "allDay": False, "rrule": None, "exdates": [], "alarmMinutes": "",
    }]


def test_subject_colour_travels_with_the_event_when_there_is_one():
    _, calendar = merged({}, [feed_event(color="#ff9500"), feed_event(uid="2026-10-12-1@lifeos", color=None)])

    assert calendar["events"][0]["color"] == "#ff9500"
    assert "color" not in calendar["events"][1]


def test_colour_is_the_users_unless_asked_for():
    data = {}
    _, calendar = merged(data, [feed_event()])
    calendar["customColor"] = calendar["color"] = "#ff00ff"  # picked in Kalendarix

    assert client.merge(data, [feed_event()], "EduPage rozvrh") is False
    assert calendar["customColor"] == "#ff00ff"

    assert client.merge(data, [feed_event()], "EduPage rozvrh", "#a6e3a1") is True
    assert calendar["customColor"] == calendar["color"] == "#a6e3a1"


def test_whole_day_event_spans_local_midnight_to_midnight():
    holiday = feed_event(start="2026-10-13T00:00:00+02:00", end="2026-10-14T00:00:00+02:00", all_day=True)

    _, calendar = merged({}, [holiday])

    assert calendar["events"][0]["allDay"] is True
    assert calendar["events"][0]["start"] == "2026-10-12T22:00:00.000Z"
    assert calendar["events"][0]["end"] == "2026-10-13T22:00:00.000Z"


def test_same_feed_again_changes_nothing():
    data = {}
    merged(data, [feed_event()])

    changed, _ = merged(data, [feed_event()])

    assert changed is False


def test_update_replaces_feed_events_but_keeps_what_the_user_changed():
    data = {}
    _, calendar = merged(data, [feed_event(), feed_event(uid="2026-10-12-1@lifeos", title="Fyzika")])
    calendar["name"] = "Škola"
    calendar["visible"] = False
    calendar["events"].append({"uid": "kx-moja", "title": "Doučovanie"})

    changed, calendar = merged(data, [feed_event(title="Zrušené: Matematika")])

    assert changed
    assert [e["title"] for e in calendar["events"]] == ["Doučovanie", "Zrušené: Matematika"]
    assert calendar["name"] == "Škola" and calendar["visible"] is False


def test_file_changed_by_kalendarix_meanwhile_is_not_overwritten(tmp_path):
    path = tmp_path / "calendars.json"
    path.write_text('{"calendars": []}', encoding="utf-8")
    before = path.stat()
    path.write_text('{"calendars": [{"id": "new"}]}', encoding="utf-8")

    assert client.write_if_unchanged(path, before, "{}") is False
    assert json.loads(path.read_text(encoding="utf-8")) == {"calendars": [{"id": "new"}]}
    assert list(tmp_path.iterdir()) == [path]  # no temp file left behind


def test_unreachable_backend_leaves_the_file_alone(tmp_path, monkeypatch, capsys):
    path = tmp_path / "calendars.json"
    path.write_text('{"calendars": []}', encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["sync", "--url", "http://127.0.0.1:9", "--file", str(path), "--attempts", "1"])

    assert client.main() == 0
    assert path.read_text(encoding="utf-8") == '{"calendars": []}'
    assert "unreachable" in capsys.readouterr().out


def test_broken_calendar_file_is_never_overwritten(tmp_path, monkeypatch):
    path = tmp_path / "calendars.json"
    path.write_text('{"calendars": [', encoding="utf-8")  # Kalendarix caught mid-write
    monkeypatch.setattr(client, "fetch_events", lambda url, attempts: [feed_event()])
    monkeypatch.setattr("sys.argv", ["sync", "--file", str(path)])

    with pytest.raises(json.JSONDecodeError):
        client.main()
    assert path.read_text(encoding="utf-8") == '{"calendars": ['


def test_real_run_writes_backup_once_and_kalendarix_layout(tmp_path, monkeypatch):
    path = tmp_path / "calendars.json"
    original = json.dumps({"calendars": [{"id": "kx-1", "name": "Rodinné", "events": []}]}, indent=2, ensure_ascii=False)
    path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(client, "fetch_events", lambda url, attempts: [feed_event()])
    monkeypatch.setattr("sys.argv", ["sync", "--file", str(path)])

    assert client.main() == 0
    written = path.read_text(encoding="utf-8")
    assert (tmp_path / "calendars.json.before-edupage").read_text(encoding="utf-8") == original
    assert written.startswith('{\n  "calendars": [\n    {\n      "id": "kx-1",\n      "name": "Rodinné"')
    assert "Učiteľ: Ján Novák" in written  # not \u-escaped, like JSON.stringify

    assert client.main() == 0  # second run: nothing to do
    assert path.read_text(encoding="utf-8") == written

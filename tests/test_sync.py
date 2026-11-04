from datetime import date, datetime

import pytest
from conftest import make_lesson

from kalendarix_edupage import edupage_client, sync
from kalendarix_edupage.store import Store


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(sync, "PAUSE_BETWEEN_DAYS", 0)
    monkeypatch.setattr(edupage_client, "connect", lambda settings: object())
    monkeypatch.setattr(edupage_client, "load_names", lambda edupage: None)


def test_sync_stores_each_day_and_records_success(settings, monkeypatch):
    monkeypatch.setattr(
        edupage_client,
        "fetch_day",
        lambda edupage, day, names: [make_lesson(date=day.isoformat())],
    )
    store = Store(settings.kx_data_dir)

    status = sync.run_sync(settings, store)

    today = datetime.now(settings.tz).date()
    assert status["ok"] and status["lessons"] == 2  # today + 1 day ahead
    assert len(store.lessons_between(today, today)) == 1
    assert store.get_meta("last_success_at") == status["at"]


def test_subject_keeps_its_colour_when_new_subjects_appear(settings, monkeypatch):
    store = Store(settings.kx_data_dir)

    def subjects(*names):
        monkeypatch.setattr(
            edupage_client,
            "fetch_day",
            lambda edupage, day, names_: [make_lesson(subject=name) for name in names],
        )
        sync.run_sync(settings, store)
        return store.get_meta("subject_colors")

    first = subjects("Matematika", "Fyzika")
    later = subjects("Chémia", "Fyzika", "Matematika")

    assert later["Matematika"] == first["Matematika"] and later["Fyzika"] == first["Fyzika"]
    assert len(set(later.values())) == 3


def test_resync_replaces_the_day_instead_of_appending(settings, monkeypatch):
    store = Store(settings.kx_data_dir)
    today = datetime.now(settings.tz).date()

    for subject in ("Matematika", "Fyzika"):
        monkeypatch.setattr(
            edupage_client,
            "fetch_day",
            lambda edupage, day, names, subject=subject: [make_lesson(subject=subject)],
        )
        sync.run_sync(settings, store)

    assert [l["subject"] for l in store.lessons_between(today, today)] == ["Fyzika"]


def test_failed_sync_keeps_cache_and_reports_error(settings, monkeypatch):
    store = Store(settings.kx_data_dir)
    day = date(2026, 10, 12)
    store.replace_day(day, [make_lesson()])

    def refuse(settings):
        raise edupage_client.EdupageLoginError("captcha")

    monkeypatch.setattr(edupage_client, "connect", refuse)

    status = sync.run_sync(settings, store)

    assert status == store.get_meta("last_sync")
    assert not status["ok"] and status["error"] == "captcha"
    assert store.get_meta("last_success_at") is None
    assert len(store.lessons_between(day, day)) == 1

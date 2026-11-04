import pytest

from kalendarix_edupage.config import Settings


def make_lesson(**overrides) -> dict:
    lesson = {
        "date": "2026-10-12",
        "period": 1,
        "start": "08:00",
        "end": "08:45",
        "subject": "Matematika",
        "subject_short": "MAT",
        "teachers": ["Ján Novák"],
        "classrooms": ["204"],
        "classes": ["3.A"],
        "groups": [],
        "topic": None,
        "online_link": None,
        "cancelled": False,
        "is_event": False,
        "changes": [],
        "notes": [],
    }
    return lesson | overrides


@pytest.fixture
def settings(tmp_path) -> Settings:
    # _env_file=None keeps a developer's real .env out of the tests.
    return Settings(
        _env_file=None,
        edupage_subdomain="skola",
        edupage_username="ziak",
        edupage_password="heslo",
        kx_data_dir=tmp_path,
        kx_sync_days_ahead=1,
    )

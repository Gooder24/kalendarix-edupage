"""Pull the timetable from EduPage into the local store."""

import logging
import threading
import time
from datetime import datetime, timedelta

from kalendarix_edupage import edupage_client
from kalendarix_edupage.config import Settings
from kalendarix_edupage.events import assign_colors
from kalendarix_edupage.store import Store

log = logging.getLogger(__name__)

# Each day costs EduPage two requests; spread them out instead of bursting.
PAUSE_BETWEEN_DAYS = 0.3

# The scheduled sync and POST /api/sync must not log in at the same time.
_lock = threading.Lock()


def run_sync(settings: Settings, store: Store) -> dict:
    """Sync today plus the configured days ahead.

    Never raises: the outcome is stored as `last_sync` and returned, so one bad
    run cannot take the scheduler down and /health can show what went wrong.
    """
    with _lock:
        started = datetime.now(settings.tz)
        status = {
            "at": started.isoformat(timespec="seconds"),
            "ok": False,
            "error": None,
            "lessons": 0,
        }
        try:
            edupage = edupage_client.connect(settings)
            names = edupage_client.load_names(edupage)
            fetched = []
            for offset in range(settings.kx_sync_days_ahead + 1):
                day = started.date() + timedelta(days=offset)
                lessons = edupage_client.fetch_day(edupage, day, names)
                store.replace_day(day, lessons)
                fetched += lessons
                time.sleep(PAUSE_BETWEEN_DAYS)
            # Kept across runs so a subject never changes its colour.
            store.set_meta(
                "subject_colors", assign_colors(store.get_meta("subject_colors", {}), fetched)
            )
            status["lessons"] = len(fetched)
            status["ok"] = True
        except edupage_client.EdupageLoginError as exc:
            log.error("EduPage sync failed: %s", exc)
            status["error"] = str(exc)
        except Exception as exc:
            # edupage-api scrapes HTML, so a site change surfaces as anything
            # from IndexError to JSONDecodeError.
            log.exception("EduPage sync failed")
            status["error"] = f"{type(exc).__name__}: {exc}"

        store.set_meta("last_sync", status)
        if status["ok"]:
            store.set_meta("last_success_at", status["at"])
        return status

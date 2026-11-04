"""HTTP API served to Kalendarix and other clients on the tailnet."""

import asyncio
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response

from kalendarix_edupage import ics, sync
from kalendarix_edupage.config import Settings, get_settings
from kalendarix_edupage.events import to_events
from kalendarix_edupage.store import Store

# How far back the calendar feed and /api/events reach, so last week stays visible.
FEED_DAYS_BACK = 30


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    store = Store(settings.kx_data_dir)

    async def sync_loop():
        while True:
            await asyncio.to_thread(sync.run_sync, settings, store)
            await asyncio.sleep(settings.kx_sync_interval_min * 60)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Without credentials there is nothing to sync; the API still serves
        # the cache and /health says what is missing.
        task = asyncio.create_task(sync_loop()) if settings.edupage_configured else None
        yield
        if task:
            task.cancel()

    def require_token(request: Request, token: str | None = Query(None)):
        if not settings.kx_token:
            return
        # Calendar subscriptions cannot send headers, hence the query fallback.
        header = request.headers.get("authorization", "")
        supplied = header.removeprefix("Bearer ") if header.startswith("Bearer ") else token
        if not supplied or not secrets.compare_digest(
            supplied.encode(), settings.kx_token.encode()
        ):
            raise HTTPException(status_code=401, detail="Invalid or missing token")

    def today() -> date:
        return datetime.now(settings.tz).date()

    def feed_lessons() -> list[dict]:
        return store.lessons_between(
            today() - timedelta(days=FEED_DAYS_BACK),
            today() + timedelta(days=settings.kx_sync_days_ahead),
        )

    app = FastAPI(title="Kalendarix EduPage", lifespan=lifespan)
    protected = [Depends(require_token)]

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "edupage_configured": settings.edupage_configured,
            "last_sync": store.get_meta("last_sync"),
            "last_success_at": store.get_meta("last_success_at"),
        }

    @app.get("/api/timetable", dependencies=protected)
    def timetable(
        date_from: date | None = Query(None, alias="from"),
        date_to: date | None = Query(None, alias="to"),
    ):
        date_from = date_from or today()
        date_to = date_to or date_from + timedelta(days=6)
        return {
            "from": date_from,
            "to": date_to,
            "last_success_at": store.get_meta("last_success_at"),
            "lessons": store.lessons_between(date_from, date_to),
        }

    @app.post("/api/sync", dependencies=protected)
    def trigger_sync():
        return sync.run_sync(settings, store)

    @app.get("/api/events", dependencies=protected)
    def events():
        # The lessons of the feed as ready-made calendar events, for clients
        # that would rather not parse iCalendar.
        return {
            "last_success_at": store.get_meta("last_success_at"),
            "events": to_events(
                feed_lessons(), settings.tz, store.get_meta("subject_colors", {})
            ),
        }

    @app.get("/calendar.ics", dependencies=protected)
    def calendar():
        body = ics.build_calendar(feed_lessons(), settings.tz, datetime.now(timezone.utc))
        return Response(body, media_type="text/calendar; charset=utf-8")

    return app

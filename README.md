<img src="assets/icon.svg" width="64" height="64" alt="">

# Kalendarix EduPage

Your school timetable from [EduPage](https://www.edupage.org) in
[Kalendarix](https://github.com/Gooder24/kalendarix), kept up to date: who teaches which lesson,
what was cancelled, substituted or moved.

It has two parts:

- **A small backend** that logs in to EduPage as you, fetches today and the next days every 30
  minutes, and keeps them in SQLite. It serves them as a JSON API and an ICS feed, so it also
  works with any calendar that subscribes to ICS.
- **A sync script for Kalendarix** (standard-library Python, run by a systemd timer every 15
  minutes). It writes the timetable into Kalendarix's `calendars.json` as one calendar, "EduPage
  rozvrh", and never touches your other calendars or events you added by hand.

What you see in the calendar:

- Back-to-back lessons of the same thing (a double lesson, a practice day, a school trip) are one
  event, with "Hodiny: 1.–5." in the description.
- Changes are named: "Odpadlo: X" (cancelled), "Suplovanie: X" (another teacher, with "namiesto: …"),
  "Zmena: X" (changed).
- Every subject keeps one colour, picked once and never changed.

EduPage has no official API. The backend uses the
[edupage-api](https://github.com/EdupageAPI/edupage-api) library, which reads the web app, and is
gentle with it: the login session is saved and reused, so EduPage does not see a login every half
hour. User-facing texts are in Slovak.

## Requirements

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- For a real EduPage login only: your school's EduPage subdomain, username and password. The tests
  need none of them.

## Quick start

This installs the project and runs its tests. It needs no EduPage login:

```bash
git clone https://github.com/Gooder24/kalendarix-edupage && cd kalendarix-edupage && uv sync && uv run pytest
```

## Usage

### Run the backend

In the cloned folder:

```bash
cp .env.example .env && chmod 600 .env   # your school's subdomain, username and password
uv run kalendarix-edupage verify-login   # logs in 3 times and checks the saved session
uv run kalendarix-edupage serve          # or as a service, see deploy/kalendarix-edupage.service
```

Two-factor login works only by confirming it in the EduPage mobile app, and is untested.

| Endpoint | What it gives |
|---|---|
| `GET /health` | status and the result of the last sync |
| `GET /api/timetable?from=2026-10-12&to=2026-10-18` | lessons as JSON |
| `GET /api/events` | calendar events, the last 30 days and ahead |
| `GET /calendar.ics` | the timetable as an iCalendar feed |
| `GET /docs` | the API documentation page that FastAPI generates |
| `POST /api/sync` | sync now |

With `KX_TOKEN` set in `.env`, everything except `/health`, `/docs`, `/redoc` and `/openapi.json` needs
`Authorization: Bearer <token>` or `?token=<token>`. Keep the backend on localhost or a private
network: it serves your timetable.

### Sync into Kalendarix

On the machine with Kalendarix:

```bash
install -D -m 755 clients/kalendarix/kalendarix_edupage_sync.py ~/.local/share/kalendarix-edupage/kalendarix_edupage_sync.py
install -D -m 644 clients/kalendarix/kalendarix-edupage-sync.{service,timer} -t ~/.config/systemd/user/
# Backend on another machine: uncomment KX_EDUPAGE_URL in the .service file.
~/.local/share/kalendarix-edupage/kalendarix_edupage_sync.py --dry-run
systemctl --user daemon-reload && systemctl --user enable --now kalendarix-edupage-sync.timer
```

Before its first write, the script copies `calendars.json` to `calendars.json.before-edupage`. It
writes atomically and skips a write when Kalendarix changed the file in the meantime. If Kalendarix
is open while the timetable changes, Kalendarix may save its older copy; the next run puts the
timetable back.

To remove it: `systemctl --user disable --now kalendarix-edupage-sync.timer`, delete the three
installed files, and delete the "EduPage rozvrh" calendar in Kalendarix.

## Tests

`uv run pytest` runs the tests of the backend and the sync script. They use made-up data and do
not contact EduPage.

`edupage-api` is pinned to an exact version on purpose: it receives your password. Read the
library's diff before bumping it.

## Accessibility

The accessibility statement, priorities, how to report a barrier and what has been tested are in
[ACCESSIBILITY.md](ACCESSIBILITY.md). Contribution rules are in [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT, see [LICENSE](LICENSE).

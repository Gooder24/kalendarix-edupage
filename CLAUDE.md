# CLAUDE.md — Kalendarix EduPage

Respond in Slovak, the maintainer's language. Code, comments and commit messages are English;
texts the user sees (CLI, errors, event titles) are Slovak.

**The repository is public. Nothing personal goes into it**: no real timetables, names, schools,
machine names or addresses, nothing about anybody's other projects. Test data is made up. Notes
about one installation belong in `NOTES.local.md`, which is gitignored; read it first if it exists.

## How it fits together

```
EduPage ─(edupage-api, 30 min)→ sync → SQLite → FastAPI ─(15 min)→ sync script → calendars.json → Kalendarix
```

Backend, `src/kalendarix_edupage/`:

- `edupage_client.py`: login, saving and restoring the session, fetching one day. It reads the raw
  day plan (`_raw_plan`, a private method of the library), because the library's parser drops
  cancelled lessons and what a substitution replaced.
- `sync.py`: today plus N days; the result goes to `/health`. Gives subjects their colours
  (`subject_colors` in the `meta` table; a colour once given never changes).
- `store.py`: SQLite cache (`data/timetable.db`), so the API works while EduPage does not.
- `events.py`: turns lessons into calendar events, used by `ics.py` and `/api/events`. Back-to-back
  lessons of the same thing become one event; status `lesson | event | substitution | changed |
  cancelled` names it ("Odpadlo: X", "Suplovanie: X", "Zmena: X"); `color` is the subject's colour.
- `api.py`, `cli.py`: the HTTP API and the commands `serve`, `sync`, `verify-login`.

Sync script, `clients/kalendarix/kalendarix_edupage_sync.py` (standard library only): reads
`/api/events` and writes one calendar into `~/.config/kalendarix/calendars.json`. It replaces only
events whose uid ends in `@lifeos` and keeps other calendars, hand-made events, and the calendar's
name, colour and visibility. `calendars.json` is a contract with Kalendarix, see its
`docs/calendars-json.md`.

The calendar id `lifeos-edupage` and the uid suffix `@lifeos` come from the project's old name.
They are stored in existing calendars, so they stay.

## Rules

- **Secrets:** the EduPage password lives only in `.env` (mode 600, gitignored), the session in
  `data/`. Never commit them, log them or print them.
- **Be gentle with EduPage:** too many logins trigger a captcha, which is why the session is
  reused. Do not shorten the sync interval or add retry loops around login.
- **`edupage-api` is pinned.** Read the source diff before bumping: it receives credentials.
- **`calendars.json` holds the user's own calendars:** write it only through the script, and run
  `--dry-run` first.

## EduPage data quirks (checked on a real plan, 10/2026)

- The same lesson can come several times, once per class group; `fetch_day` merges them.
- All-day events come as 00:00–24:00.
- A school event over several lessons comes as one record per lesson.
- A cancelled lesson has `type: ""`, the note "Odpadlo", no time (taken from the bell schedule
  `data["zvonenia"]`), and its subject only in `header[].item` with
  `changes: [{"column": "subjectid", "old": …}]`.
- Seminar groups have an internal key in `groupnames` (`seminargroup:3`); the readable name is in the
  note ("Skupina: Seminár 3").
- A substitution with another teacher or room has not been seen yet. Its handling is derived from
  the cancelled-lesson shape (`teacherids` / `classroomids` in `changes`) and needs checking when the
  first one arrives.
- `edupage.get_timetable_changes` also knows which lessons an event replaced; not used yet.

## Commands

```bash
uv sync
uv run pytest
uv run kalendarix-edupage verify-login
uv run kalendarix-edupage sync
```

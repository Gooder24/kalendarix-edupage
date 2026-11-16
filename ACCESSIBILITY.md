# Accessibility

Accessibility matters here because this project's output is what people read every school day: lessons, cancellations and substitutions. Anyone who uses a screen reader, a keyboard, magnification or other assistive technology should be able to use that output, and should be able to report a barrier without difficulty.

This document covers what the project is, what we prioritise, how to help, how to report a barrier, and what has and has not been tested.

## What the project is

Kalendarix EduPage is a Python service with no graphical user interface of its own. People meet it in three ways:

- the `kalendarix-edupage` command, used in a terminal;
- the calendar feed (`/calendar.ics`) and the JSON API, which calendar apps and Kalendarix read;
- the `/docs` page that FastAPI generates for the API.

The calendar itself is shown by Kalendarix or by the calendar app you subscribe with. Those applications are not part of this repository.

## Priorities

- **Status in words.** Event titles name the change ("Odpadlo: ..." for a cancelled lesson, "Suplovanie: ..." for a substitution, "Zmena: ..." for a changed one), so the status does not depend on colour alone.
- **Plain Slovak.** Texts that people read (command messages, event titles, error messages) are in Slovak, in plain words.
- **Easy-to-navigate documentation.** Ordered headings, descriptive link text and alternative text for images. These rules are checked automatically (see Testing).
- **No conformance claim.** We do not claim a WCAG conformance level for this repository, because the service has no interface of its own.

## Contributor expectations

- Do not skip heading levels.
- Write link text that makes sense out of context: "see the setup section", not "here" or "click here".
- Give every image alternative text. Use `alt=""` only for a purely decorative image.
- Keep user-facing texts in plain Slovak, and say in the pull request what text changed.
- Do not rely on colour alone to convey meaning.
- The project has no graphical interface. If one is ever added, its pull request must list the keyboard, screen reader and automated checks that were run, with their results.

The rest of the workflow is in [CONTRIBUTING.md](CONTRIBUTING.md).

## Reporting an accessibility barrier

Open an issue with the **Accessibility barrier** form. It adds the `accessibility` label. Please include, when you can:

- what you were trying to do, and what happened instead;
- where it happened: a command, an endpoint, or a calendar app;
- your operating system, terminal or calendar app, and your assistive technology, with versions;
- the severity (see below).

A screenshot is optional, and you do not need to disclose a disability. Issues are public, so never paste a password, a token or personal data such as your real timetable into one.

If the form does not work for you, open a plain issue with the same information.

### Severity

- **Critical:** stops you from completing a core task, such as reading today's lessons.
- **Serious:** makes a task much harder, but a workaround exists.
- **Moderate:** an annoyance or an inconsistent experience.
- **Minor:** little effect on how you use the project.

### How we respond

- We acknowledge each accessibility issue with a comment.
- We confirm the severity, and add `good first issue` or `help wanted` when the work suits a newcomer or needs outside expertise.
- Where possible, we suggest a workaround while a fix is in progress.
- We post status changes as comments on the issue.
- Before we close an issue, we may ask you to confirm that the fix works for you.
- We do not publish response times yet.

## Ownership

The repository maintainer, GitHub account `Gooder24`, owns accessibility for this project. The owner:

- triages accessibility issues and sets their severity and labels;
- keeps this document and the issue form current;
- records which checks were run, and their results, under Testing.

## Supported environments

- **Operating system:** Debian 13 (Linux). Tests were run here.
- **Python:** 3.13, as the project requires.
- **Terminal:** the command was used in a terminal. No screen reader has been used with it.
- **Calendar apps:** the feed has not been tested with any calendar app.
- **Browsers:** the `/docs` page has not been tested in any browser.

## Known limitations

- No assistive technology has been used with any output of this project yet.
- The `/docs` page comes from FastAPI, and we have not checked its accessibility.
- Calendar apps decide how they show the feed. That is outside this repository.
- Texts that people read are in Slovak only. There is no translation and no language switch.

If you find a barrier that is not listed here, please [report it](#reporting-an-accessibility-barrier).

## Testing

- **Automated, documentation:** `.github/scripts/check-docs.py` checks heading order, image alternative text and link text in every Markdown file. It runs on each pull request and on pushes to `main`. A new problem fails the check. Problems that existed before are listed in `.github/a11y-baseline.json`.
- **Keyboard only:** not applicable. There is no graphical interface to test. The command is used from a terminal.
- **Screen reader:** not done yet. To do it: start a screen reader (for example NVDA or Orca), run `kalendarix-edupage --help` in a terminal and listen to the output, then subscribe to a feed in a calendar app and check that event titles read clearly. Record the environment in an issue.
- **Manual checks (zoom, reflow, colour contrast):** not applicable, for the same reason as keyboard checks.
- **Documentation review:** the checks above cover structure and links. No person who uses assistive technology has reviewed this document yet.

## Dependencies

The runtime dependencies are `edupage-api`, `fastapi`, `uvicorn` and `pydantic-settings`. Only FastAPI produces a page a person might see, the `/docs` page above. We have not checked the accessibility of these dependencies, and no upstream accessibility issue is tracked for them. A new dependency that has a user interface is checked for accessibility before it is added, and the result is noted in the pull request.

## Community

- **Ways to help:** look for issues labelled `accessibility`. `good first issue` marks small tasks; `help wanted` marks tasks that need expert help. Questions and feedback are welcome in issues.
- **Recognition:** with your consent, accessibility contributions are named in the release notes.
- **Progress:** with each release, the owner posts what accessibility work was done, what is still open, and the known limitations.
- **Resources:** `.github/scripts/check-docs.py` needs only Python 3 and git and can be copied into another project. The owner maintains it.
- **Not in place yet:** a code of conduct, and a private contact for accommodation requests.

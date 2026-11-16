# Contributing

Thank you for helping. Please read [ACCESSIBILITY.md](ACCESSIBILITY.md) first: it lists the accessibility expectations for contributions and how to report a barrier.

## Set up and test

```bash
uv sync
uv run pytest
```

The tests use made-up data and do not contact EduPage.

## Before you open a pull request

- Run the tests, and fill in the accessibility section of the pull request template.
- Documentation changes must pass the documentation check, which CI also runs: `python3 .github/scripts/check-docs.py`.
- Keep texts that people read in plain Slovak, as the project does.
- Never commit `.env`, `data/`, or real timetable or personal data.
- Read the library's diff before you change the `edupage-api` pin (see the README).

## Reporting problems

- Accessibility barriers: use the **Accessibility barrier** issue form.
- Other bugs: open an issue.

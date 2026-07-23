# Xoltra Backend Tests

37 tests, all credential-free, none of them call Cohere, Stripe, Google, or
Microsoft. They cover the business logic that lives entirely in the
database: RBAC/orgs, referrals, the template marketplace, workflow-import
parsing and graph compilation, weekly digest stats, field encryption, and
audit-log tenant scoping.

## Running

```
pip install pytest
cd backend
pytest tests/
```

## What's NOT covered here, on purpose

Anything that calls an external API needs real credentials or mocks to test
properly, neither of which this suite attempts:
- `workflow_import.py`'s actual LLM call inside `parse_import()` (the
  parsing/compilation logic around it IS tested, see `test_workflow_import.py`)
- Stripe checkout creation and webhook handling end-to-end
- Google OAuth / OTP email delivery
- OneDrive token exchange with Microsoft's servers

A second suite built around mocking those specific calls is the natural
next step, not attempted here.

## A real bug this suite caught while being written

`conftest.py`'s `db` fixture originally only reset `knowledge_db`'s
connection cache between tests. That wasn't enough: nearly every module in
this codebase (`auth`, `referrals`, `teams`, `templates`, `workflow_engine`,
`workflow_store`, `subscription_manager`, `onedrive_routes`,
`personalization`, `projects`, `moderation`) guards its own table-creation
with a module-level "already ran once" boolean, correct for a real
long-running server, but it means a second test in the same process would
silently skip creating tables in its brand-new database, because the flag
from the first test was still `True`. Every one of those flags gets reset
per test now, not just the connection. Worth knowing if a 12th module gets
the same pattern added later, it'll need adding to `conftest.py`'s reset
list too.

## A note on how this suite was verified

Real `pytest` could not be installed in the sandbox this was built in (no
network access to PyPI). Every test file here uses standard, unmodified
pytest conventions (`@pytest.fixture`, `pytest.raises`, the built-in
`tmp_path` fixture, a `monkeypatch` fixture) and should run correctly under
real pytest without changes. To actually prove that rather than just
assert it, a minimal pytest-compatible fixture resolver was built
temporarily (not included in this repo) and used to execute these exact
files, all 37 tests passed. Worth re-running under real pytest once
installed, as a final confirmation, but the logic has been exercised, not
just written.

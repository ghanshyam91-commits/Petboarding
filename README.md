# SafeStay — India-first pet boarding

**Verified boarding with evidence of care.** Python / Django application in the Petboarding repository.

## Current delivery

This is a working, server-rendered **initial implementation**, not a completed production marketplace. It includes real database-backed parent, provider and trust workflows. It does not charge money, deliver emergency alerts, supply real verified providers, or provide a booking-protection guarantee. Read [implementation status](docs/IMPLEMENTATION_STATUS.md) before deploying.

### Run locally

Python 3.12 recommended.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export DEBUG=true
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000. Accounts are currently invitation-based username/password accounts. Django administration lives at `/admin/`.

### Optional fictional demo

Run only on a local development database. Choose your own password; none is committed.

```bash
export DEMO_PASSWORD='choose-a-unique-password-of-at-least-12-characters'
python manage.py seed_demo
```

Sign in as `parent_demo`, `provider_demo`, or `trust_demo` using that password. The demo has Uno, three **fictional** Bengaluru facilities, a live stay and sample care events. Its verification records and jurisdiction policy are fixtures, **not legal or veterinary facts**. Demo seeding refuses to run with `DEBUG=false`. Use a separate database for real records.

### Workspaces

| Path | Purpose |
|---|---|
| `/` | Parent home transforms into the active-stay timeline |
| `/explore/` | City/date/multi-pet search with server-side hard eligibility |
| `/profile/` | Pet passports, health status and privacy requests |
| `/bookings/` | Household stays |
| `/stays/<id>/` | Care timeline, quote, handover, messages, emergency and disputes |
| `/operations/` | Provider/caregiver care board and active pets |
| `/trust/` | Staff-only incident triage, critical tasks and suspension |
| `/admin/` | Restricted Django administration and verification records |

### Tests

```bash
DEBUG=true python manage.py test
DEBUG=true python manage.py makemigrations --check --dry-run
```

The PostgreSQL tests exercise simultaneous capacity reservations and database-level evidence immutability. SQLite skips those tests and is suitable only for local exploration. CI uses PostgreSQL 16. `select_for_update` does not provide row locking on SQLite; see [Django QuerySet documentation](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update).

### Architecture

Django templates keep frontend rendering, localization and session/CSRF controls straightforward. The warm cream/forest visual system is responsive and includes labelled forms, keyboard focus, reduced-motion support and textual safety states. Accessibility certification and browser/device verification are not claimed.

`care/services/stays.py` owns transactional reservations, cancellation, handover, task completion and incident escalation. Domain state changes do not belong in generic CRUD endpoints. PostgreSQL provider-row locks serialize capacity writers; health and compatibility checks run again inside the reservation transaction. Every pet is checked individually. Financial amounts are integer paise.

Care events, custody, audit, consent and ledger entries are append-only. PostgreSQL triggers reject UPDATE and DELETE, including bulk ORM operations. Database owners can still alter schema: production requires least-privilege roles, backup controls and independent retention infrastructure. No immutable object-store evidence retention is claimed.

Credentials expose category, reviewer, verification time and expiry, rather than a single unexplained badge. Unreviewed jurisdictions fail closed. Residential street addresses and document storage keys are not rendered publicly.

### Background processing

```bash
python manage.py escalate_care
```

Run every minute via a scheduler. It creates one incident and critical notification records for each previously un-escalated overdue critical task. Notification records are **queued only**: external delivery, retries, fallback and acknowledgements still need implementation. Do not rely on this app as an emergency alert service.

### Deployment preparation

Dockerfile, Gunicorn and Railway configuration are included. No deployment has been performed. Set `DEBUG=false`, a strong `SECRET_KEY`, PostgreSQL `DATABASE_URL`, exact `ALLOWED_HOSTS` and HTTPS `CSRF_TRUSTED_ORIGINS`. Configure trusted reverse-proxy HTTPS handling for the chosen host; never trust arbitrary forwarded headers. Run `python manage.py check --deploy` and follow [Django's deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/).

Before public use, complete the launch gates in the status document: real authentication integrations, admin MFA, private media scanning/storage, reviewed local compliance, payment webhooks, emergency delivery, observability, backups, access review and end-to-end QA. The provided Docker configuration does not make these integrations complete.

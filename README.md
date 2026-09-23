# SafeStay

**Verified boarding with evidence of care** is the idea behind SafeStay, an India-first pet boarding prototype built with Django.

The problem felt concrete to me as a pet owner: finding a facility is only the first step. I also want to know whether it can actually take my dog, what happens at handover, who did the care tasks, and what the platform can show if something goes wrong. The demo pet, Uno, and the Bengaluru facilities in this repository are **fictional test data**.

This is an initial implementation, not a live booking marketplace. It has database-backed parent, provider and trust workflows. It does not take payments, verify real facilities, deliver emergency alerts or promise replacement boarding. [Implementation status](docs/IMPLEMENTATION_STATUS.md) tracks the gaps in detail.

## Follow a stay

1. A parent maintains a pet profile and health record, then searches by city, dates and pets. Eligibility checks exclude incompatible providers before a reservation can be made.
2. A reservation takes nightly capacity for **each** pet. The service checks eligibility again inside the transaction; PostgreSQL row locks protect concurrent reservations.
3. Handover records belongings, food, condition and both parties' acknowledgement. During an active stay, attributed care events and per-pet tasks appear in the timeline.
4. Overdue critical tasks can be escalated into incidents and queued notification records. Those records currently have **no external delivery**.

There are separate parent, provider and trust workspaces. The trust view can see incidents and suspend a provider from new reservations. Prices are represented in integer paise, but the quote is an estimate and no money changes hands.

The point of the data model is that a stay leaves a useful trail: care events, custody changes, consent, ledger and audit entries are append-only. PostgreSQL triggers reject updates and deletes to these records. This protects against ordinary application writes; a database administrator can still change schema or data, so stronger evidence retention needs infrastructure beyond this repo.

## Run locally

Python 3.12 is recommended.

```bash
git clone https://github.com/ghanshyam91-commits/Petboarding.git
cd Petboarding
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DEBUG=true
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000/. To explore the three workspaces with local fictional data:

```bash
export DEMO_PASSWORD='choose-a-unique-password-of-at-least-12-characters'
python manage.py seed_demo
```

Sign in as `parent_demo`, `provider_demo` or `trust_demo` with that password. The seeder requires `DEBUG=true` and a fresh development database. Its facility credentials and city rule are examples, not real verification.

| Area | URL | What you can inspect |
| --- | --- | --- |
| Parent | `/`, `/explore/`, `/profile/`, `/bookings/` | Pet profile, eligibility, search and stays |
| Stay | `/stays/<id>/` | Quote, handover, care timeline, messages and incident flow |
| Provider | `/operations/` | Active pets and care tasks |
| Trust | `/trust/` | Incident triage and provider suspension |
| Admin | `/admin/` | Restricted Django administration |

## Engineering notes

The user interface uses Django templates and session/CSRF protection. The stay service in `care/services/stays.py` owns reservations, cancellation, handover, task completion and escalation; those state changes are deliberately kept out of generic model edits. Credentials expose their category, reviewer and expiry. Unreviewed city rules fail closed. Private addresses and document keys are not displayed in public listings.

Run the suite and migration check with:

```bash
DEBUG=true python manage.py test
DEBUG=true python manage.py makemigrations --check --dry-run
```

SQLite is convenient for a first look, but it does not enforce the same row-locking behavior as PostgreSQL. CI runs PostgreSQL 16 tests for concurrent reservations and append-only triggers. The command `python manage.py escalate_care` is intended to run every minute under a scheduler; it only creates incident and notification records.

## Before a real pilot

The included Dockerfile, Gunicorn and Railway settings are deployment starting points. A hosted demo still needs exact hosts, HTTPS and CSRF configuration, a strong secret, PostgreSQL, and `python manage.py check --deploy`. A real pilot additionally needs provider and health-document verification, private media handling, reliable emergency notification delivery, stronger authentication, reviewed local rules, backups, payments/refunds if money is involved, and hands-on browser and device testing. See the [launch gates](docs/IMPLEMENTATION_STATUS.md) for the full list.

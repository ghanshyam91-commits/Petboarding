# Requirement coverage and launch gates

The original brief describes a large safety-critical marketplace. This file distinguishes working code from schema, adapters and unfinished workflows. Nothing listed as pending should be represented as supported in marketing.

| Brief area | Current implementation | Still required |
|---|---|---|
| Safe Stay lifecycle | Unpaid reservation, handover service/UI, active care and cancellation | Paid confirmation, checkout transition, complete state machine and expiry of unpaid holds |
| India launch cities/species | Seven cities, separate dog/cat values and species eligibility | City onboarding, cat-specific routines/environment rules; later species |
| Authentication | Django sessions, invitation accounts, shared database login throttle | Phone OTP, verified email/Google login, registration/recovery, device sessions, MFA |
| Pet passports | Persistent household pets; core profile form; health/behaviour/routine/emergency JSON | Full structured editing, secure photo/document uploads, per-field verification, health access policy |
| Health | Records, verification identity/date/expiry, booking blocks | Upload review workflow, expiry notifications, species-specific vaccine policy |
| Provider passport | Providers, credentials and structured audit field | Full onboarding, inspections, staff training UI and reviewer workflows |
| Provider profile | Facility cards and credential evidence | Complete profile, real images, geolocation, availability calendar, reliability metrics |
| Search | Exact selected city/date/pets, safe eligible results | Radius/route-time map, amenity filters, provider comparison; no distance claims are made |
| Matching | Hard exclusions before simple supervision/price ordering | Explainable weighted fit score with measured reliability; no invented percentage |
| Capacity | Transactional nightly capacity and blocked-day model; PostgreSQL concurrency test | Species/size/room/staff constraints, timed check-in/out, hold TTL, self-service calendar |
| Multi-pet | All pets validated and capacity counted; independent care snapshots/tasks | Combined handling compatibility and household-specific pricing policies |
| Trials | Trial model and administrative record | Parent/provider scheduling, private-note enforcement and suitability workflow |
| Pricing | Integer-paise base/additional-pet estimate | Taxes, peak dates, medication/transport/late fees, price lock and policy versioning |
| Payments | Disabled adapter contract, append-only ledger model | UPI/card/net-banking provider, signed idempotent webhooks, refunds, payout/reconciliation and dispute holds |
| Handover | Both-party acknowledgement, conditions/belongings/food, custody events | Photos, verified real emergency contact, checkout and transport custody |
| Care timeline | Structured attributed events rendered from database | Media, real-time streaming, corrections as superseding events |
| Care tasks | Routine-generated per-pet tasks, completion, late status, critical escalation command | Typed regimen validation, medication competency per staff, due/missed grace periods, schedule changes |
| Live updates | Timeline and stay conversation | Photo/video ingestion, preferences, push and real-time delivery |
| CCTV | Vendor interface only | Access tokens, viewing windows, access logs, incident holds, vendor integration |
| Emergencies | Incident, timestamped care/audit record, evidence flag, queued notifications | Contact escalation, treatment-authority enforcement, incident steps, emergency service integrations |
| Vet escalation | Data can reference pet emergency/health information | Vet directory/location lookup, tele-vet, hospital workflow and documents |
| Incident evidence | Database append-only records, evidence hold flag | WORM media storage, hashes, linked evidence manifest, enforced retention and export |
| Backup boarding | Safe search service reusable | Automatic provider-cancellation replacement/refund orchestration |
| Transport | Custody-event primitive | Drivers, vehicles, OTPs, GPS, photos, restraint checks, tracking UI |
| Reviews | Completed-owner-only submission endpoint and model | Review form/profile display, moderation and anti-retaliation policy enforcement |
| Trust & Safety | Staff dashboard, suspension blocks reservations, incident summaries | Fine-grained staff grants, full investigations, evidence request, appeals and case resolution |
| Disputes | Case creation linked to stay; evidence flag; audit | Unified case UI, party responses, decision/refund/insurance flow |
| Insurance | Terms model and adapter contract | Insurer integration, coverage rendering, claims; no protection badge shown |
| Provider operations | Active stays, attributed tasks, overdue counts | Calendar, arrivals/departures, revenue, compliance reminders and SaaS administration |
| Staff | Membership roles and caregiver authorization | Staff invitations, assignment, training expiry and granular pet-level permissions |
| Compliance | Versioned effective city rule, required credentials/vaccines, fail-closed unreviewed rule | Rule predicates by service/provider type, legislative review, effective-date coverage for future stays, full audit/version immutability |
| Admin control centre | Safety KPIs, incidents, provider suspension; restricted Django admin | Remaining operational sections and authorization beyond is_staff |
| Notifications | Queued model plus adapter contract | Actual channels, retry/fallback, delivery/acknowledgement, on-call SLA |
| Localization | Django translation tags in templates, India timezone/INR, seven language definitions | Translated catalogs and localized validation/status strings, language switcher |
| Privacy | Hidden residential addresses/doc keys, consent schema and export/deletion request queue | Private encrypted storage, medical access audit, fulfillment, retention enforcement and reviewed DPDP policies |
| Security | Sessions, CSRF, template escaping, ORM, login throttle, TLS settings, production PostgreSQL enforcement | Admin MFA, secure uploads, encryption/key management, full RBAC/access logging, penetration/security review |
| Accessibility | Semantic forms, focus styles, skip link, reduced motion, responsive CSS | WCAG 2.2 AA audit, screen reader/device/contrast testing and video captions |
| Design | Parent active-stay home; Explore, Bookings, Messages, Profile; provider and trust views | Real facility/pet images, additional workflows, browser visual validation |

## Verification at initial delivery

- Local test suite: 21 passed and 2 PostgreSQL-only tests skipped.
- GitHub Actions passed the full suite against PostgreSQL 16, including concurrent capacity reservations and append-only database triggers: https://github.com/ghanshyam91-commits/Petboarding/actions/runs/35683967685
- Browser smoke script was attempted, but the required Chromium download was unavailable in the execution environment. Layout screenshots and cross-browser verification have not been completed.
- No external payment, messaging, CCTV, map, insurance or veterinary integration has been tested.
- No public deployment, real provider verification, legal validation or production-readiness certification has been performed.

## First launch milestone

Keep any hosted instance private and use synthetic data until authentication/MFA, private media, local rule review, verified provider onboarding, full booking state transitions, health/emergency consent and real alert delivery are operational. Then enable a closed pilot with an on-call care team and real incident drills. Paid launch follows webhook/refund reconciliation, transparent tax pricing, expiry of unpaid capacity holds, concurrency testing and backup/restore validation.

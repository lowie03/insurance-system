# Known assumptions and limitations

## Brokers share one token: the log proves *a* broker acted, not *which* broker

`BROKER_API_TOKEN` (see `backend/app/dependencies.py: require_broker`) is a single shared secret
checked against the `X-Broker-Token` header — there are no per-broker accounts yet. Every broker
action is still written to `audit_log` (action, target, reason, broker_note, config_versions), so
there's a complete record that *some* authorized broker took the action, when, and why — but not
*who*, since the token doesn't identify an individual. Anyone who leaks or shares the token is
indistinguishable from any other broker in the log. Fixing this needs real per-broker accounts
(login, one token/session per person) — out of scope for this prototype.

**NDPR note:** `GET /broker/queue` is the most personal-data-heavy endpoint in the system —
referrals return full recommendations and exclusions (health, income-derived, and vehicle/property
signals), and stuck/failed payments return basket contents and amounts — and it is guarded only by
that one shared token, not by an individually attributable account. Broker access is therefore
**authenticated but not individually attributable**: the system can prove *someone* with the token
viewed or acted on this data, but not which natural person. Per-broker accounts with role-based
access are required before any real deployment handling real customers' data; this prototype
accepts that gap explicitly rather than leaving it implicit.

## "Refunded" is a record, not an action: we never call Paystack's refund API

`POST /broker/payments/{reference}/resolve` with `outcome: "refunded"` only records, in our own
database and audit log, that a broker says the customer was refunded. It does **not** call
Paystack's refund endpoint or move any money — the broker must actually issue the refund through
the Paystack dashboard (or Paystack's API directly) themselves, outside this system. The response
text says this explicitly so it's never mistaken for an automated refund.

## Duplicate purchases are only detected within one quote

There are no user accounts yet. Each `POST /quotes` mints a fresh `customer_id`
(`CUS-XXXXXXXX`), so nothing links two quotes made by the same real person. The
duplicate-purchase check (`backend/app/services/duplicate_check.py`) can therefore only see
policies already active **on the same `quote_id`** — it refuses re-buying a product (or its
mutually-exclusive alternative, e.g. HFM after HIN) within one quote's lifetime, but a customer
who requests a *second* quote can still buy the same product again under the new `quote_id`.

Fixing this properly needs real identity: either accounts (login before quoting) or a durable
customer key collected at quote time (e.g. verified phone number) that quotes can be looked up
by. Until then, this is a conscious gap, not a bug.

## Certificates live in the database, not on disk

`Policy.pdf_bytes` holds the certificate itself (a `LargeBinary` column, ~5KB per policy), not a
path to a file on disk. This is specifically because Render's free web service tier has an
ephemeral filesystem — wiped on every restart, redeploy, and spin-down after idling — and can't
attach a persistent disk, so anything written to local disk would vanish. Storing the bytes
directly in the same row as the policy also means issuance stays genuinely all-or-nothing: a
transaction rollback discards the certificate together with the policy, with no separate file to
clean up on failure (the old path-on-disk design needed an explicit unlink-on-rollback step; this
doesn't).

This suits a prototype at this volume (a few KB per policy, no real traffic), but doesn't scale: a
production system issuing many policies should use object storage (e.g. S3 or R2) for the PDF
itself, with the database holding only a key/URL — not the database doing double duty as a file
store. Swapping this in later means changing `_issue_one_policy()` and the certificate route; the
`Policy` row's shape (one `pdf_bytes`-or-`pdf_key` column) stays the same either way.

## `dev.db` lives outside `~/Documents`

This project's checkout sits under `~/Documents`, which has iCloud's "Desktop & Documents Folders"
sync enabled. That sync daemon intermittently denies writes to freshly created files (and the
sidecar journal file SQLite creates for every transaction) inside synced directories — the app hit
this directly as `sqlite3.OperationalError: attempt to write a readonly database` on the very first
`POST /quotes`. It's the same underlying issue as the earlier "hidden .pth file" venv problem: iCloud
File Provider interfering with generated files, not a bug in the app.

Fix: `DATABASE_URL` in `.env` points at `~/Library/Application Support/insurance-system/` instead
of the project folder — `~/Library` is not iCloud-synced. `.env.example` documents the pattern for
setting this up elsewhere. This only matters for local development: a real deployment's database is
Neon Postgres, not a local SQLite file, so it's never exposed to this class of bug at all. If you
ever see this error again locally, it means something is writing inside the synced project tree;
move it out the same way.

## `dev.db` must be recreated after the basket-checkout change

The app uses `Base.metadata.create_all()` (see `backend/app/main.py`) rather than migrations, so
schema changes never apply to an existing SQLite file automatically. The basket-checkout change
altered the `payments` and `policies` tables (new `payment_items` table; `payments` lost
`product_code`/`payment_plan`; `policies` moved from a lone unique `payment_reference` to a
composite unique `(payment_reference, product_code)`). **Delete `dev.db` before running the app
again** — `rm dev.db` from the project root — so it gets rebuilt with the new schema. Tests are
unaffected: each one gets its own fresh temporary database.

# Insurance Recommendation & Automated Policy Issuance System

A web system that recommends suitable non-life insurance products to Nigerian users and issues a
signed, verifiable policy certificate in under a minute.

The design principle throughout is **the model recommends, the rules decide**. A gradient-boosted
model predicts which products a person is likely to need; deterministic rules loaded from YAML decide
what may actually be offered, what it costs, and whether the person can afford it. Every refusal
carries a reason, and every recommendation and issuance is written to an audit log with the model and
config versions that produced it.

Built as a final-year computer science project. **The certificates it issues are watermarked
prototypes and are not valid insurance contracts.**

---

## What it does

1. A person answers a short profile form (five steps, ~20 fields, income optional).
2. The recommender scores all eight products; rules remove the ineligible and unaffordable ones.
3. The person sees their top matches with a full premium breakdown, plus **everything that was ruled
   out and why**.
4. They can select several products; the system checks the combined cost against a basket budget and
   switches payment plans to monthly where a lump sum would not fit their cash flow.
5. One Paystack payment issues all selected policies in a single database transaction.
6. Each policy gets a check-digited number, an HMAC signature, and a PDF certificate with a QR code
   that anyone can scan to verify the policy is genuine.
7. Anyone the system cannot serve — no affordable product, weak match, or a payment that went through
   without a policy — lands in a broker queue for a human.

## Objectives and status

| Objective | Target | Status |
|---|---|---|
| 1. Recommendation quality | Right product in top 3 | **Met.** Hit@3 97.2% ± 0.1 overall, 89.4% ± 0.4 on non-dominant products (Zimnat) |
| 2. Issuance speed | ≤ 60 seconds | **Met.** Median 0.03–0.11 s end to end over HTTP |
| 2. Faster than conventional | ≥ 70% reduction | **Pending** — needs a measured baseline for manual issuance |
| 3. Usability | 30+ testers, 80% satisfied | **Pending** — study not yet run |

---

## Architecture

Dependencies flow in one direction only:

```
frontend  ->  backend  ->  insurance_core  ->  config/
```

`insurance_core` is pure Python: no web framework, no database. The same `recommend()` that was
validated in the notebooks is the one that serves live users.

```
insurance-system/
├── config/                  Business rules as data (YAML + CSV), each file versioned
├── insurance_core/          Recommender, rules, pricing, payments, basket, issuance
│   └── issuance/            Policy numbering, HMAC signing, PDF certificate
├── backend/app/             FastAPI: routes, services, SQLAlchemy models
├── frontend/                React + Vite + Tailwind
├── training/                Scripts that reproduce the experiments and build the model
├── data/synthetic/          Generated Nigerian customer data (committed)
├── data/raw/                Zimnat competition data (NOT committed — see below)
├── artifacts/               Trained models (gitignored) and metric reports
├── tests/                   104 tests: core logic, API, payments
└── docs/                    Assumptions, technical documentation, thesis material
```

---

## Running it locally

### Requirements

- Python 3.12 (pinned in `.python-version`)
- Node.js 20+
- macOS only: `brew install libomp` (LightGBM needs it)

### Setup

```bash
git clone https://github.com/lowie03/insurance-system.git
cd insurance-system

python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,backend]"

cp .env.example .env
```

Edit `.env` and set at least:

```bash
POLICY_SIGNING_KEY=<python -c "import secrets; print(secrets.token_hex(32))">
BROKER_API_TOKEN=<another 64-character random string>
PAYMENT_MODE=simulated          # or paystack, with a test key below
PAYSTACK_SECRET_KEY=sk_test_...
```

Build the model (the trained file is not committed — it is rebuilt from the committed data):

```bash
python training/train_recommender.py
```

This should print `best number of trees: 168` and LightGBM at `0.623 / 0.946`. Those exact numbers
confirm your environment reproduces the reported results.

### Run

```bash
# terminal 1 — API on http://localhost:8000  (interactive docs at /docs)
uvicorn backend.app.main:create_app --factory --reload

# terminal 2 — web app on http://localhost:5173
cd frontend && npm install && npm run dev
```

Pages: `/` the form, `/quotes/:id` recommendations, `/payment` post-payment, `/verify/:number` public
policy check, `/broker` the broker queue.

### Tests

```bash
pytest                                   # all 104
pytest tests/backend -s -k objective     # prints the issuance timing
```

---

## Reproducing the experiments

| Script | What it does |
|---|---|
| `training/generate_synthetic.py` | Builds the synthetic Nigerian dataset (seeded, reproducible) |
| `training/zimnat_experiments.py` | Reproduces the Zimnat evidence: baselines, the v1 failure and its diagnosis, the regularised model, calibration and stability |
| `training/train_recommender.py` | Trains and saves the deployed model, writing metrics to `artifacts/reports/` |

**The Zimnat data is not in this repository.** The competition rules forbid redistributing it. To run
`zimnat_experiments.py`, download `Train.csv` from the
[Zimnat Insurance Recommendation Challenge](https://zindi.africa/competitions/zimnat-insurance-recommendation-challenge)
on Zindi (free account, accept the rules) and place it in `data/raw/zimnat/`. That folder is
gitignored.

---

## Deployment

| Piece | Service |
|---|---|
| Backend | Render (free web service) |
| Database | Supabase Postgres (use the **session pooler** connection string — the direct one is IPv6-only) |
| Frontend | Vercel (root directory `frontend`) |

**Build command:**
`pip install -r requirements.txt && pip install -e . --no-deps && python training/train_recommender.py`

**Start command:**
`uvicorn backend.app.asgi:app --host 0.0.0.0 --port $PORT`

`render.yaml` describes the service. `requirements.txt` holds pinned versions so the deployment runs
what was tested; `pyproject.toml` declares which packages are needed. Regenerate the pins with
`pip freeze --exclude-editable > requirements.txt` after changing dependencies.

### Environment variables

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres in production, SQLite locally. `postgres://` and bare `postgresql://` are rewritten to use the psycopg 3 driver |
| `POLICY_SIGNING_KEY` | Signs policy records. **Changing it invalidates every existing certificate** |
| `BROKER_API_TOKEN` | Shared secret for `/broker` routes |
| `PAYMENT_MODE` | `paystack` or `simulated` |
| `PAYSTACK_SECRET_KEY` | Test key only; live keys are refused unless `ALLOW_LIVE_KEYS=true` |
| `API_BASE_URL` | Used to build certificate download links |
| `FRONTEND_ORIGINS` | Comma-separated CORS allow-list |
| `VERIFY_BASE_URL` | Where QR codes point (frontend `/verify`) |
| `PAYSTACK_CALLBACK_URL` | Where Paystack returns the customer (frontend `/payment`) |

Set the Paystack **test** webhook URL to `https://<your-api>/payments/webhook`.

### Known limits of the free tiers

- Render free services sleep after 15 minutes idle; the first request then takes 30–60 seconds.
- Supabase free projects pause after 7 days with no database activity. Data is retained and the
  project can be restored, but a scheduled query keeps it awake.

---

## Security notes

- Policy numbers carry a Luhn check digit, so any single mistyped digit is caught before a lookup.
- Each policy is signed with HMAC-SHA256 over its key fields. The public `/verify` endpoint recomputes
  the signature and reports `SIGNATURE_MISMATCH` if a certificate has been altered.
- `/verify` is public and deliberately minimal: status, product and expiry only. No names, no amounts.
- Certificate and policy links require the signature, acting as a per-policy password until user
  accounts exist.
- Payment is confirmed by asking Paystack directly, never by trusting the browser. The amount and
  currency must match exactly.
- One payment reference can produce at most one policy per product, enforced by a database constraint.

## Known limitations

Documented in full in `docs/assumptions.md`. The main ones:

- **Health, travel and property prices are illustrative.** Only the NAICOM motor tariff and the 5%
  comprehensive minimum are real regulation.
- **The deployed model is trained on synthetic data.** Evidence that the method works comes from
  Zimnat (real African insurance data); the synthetic model demonstrates the system end to end.
- **No user accounts.** Duplicate-purchase protection is scoped to a single quote.
- **One shared broker token**, so the audit log proves *a* broker acted, not which one.
- **Refunds are recorded, not executed.** A broker refunds in the Paystack dashboard separately.
- **Monthly plans collect only the first instalment.** Recurring charges are future work.

## Licence and data

Code is the author's academic work. The Zimnat dataset is subject to Zindi's competition terms and is
not redistributed here. Synthetic data is generated by this repository and carries no restrictions.

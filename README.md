# Restaurant Management System

A billing, WhatsApp chatbot, dine-out booking, and customer retention system for small and medium restaurants. The first market is **metro cities, starting with Delhi**.

Planning documents are in [`plans/`](plans/01-discussion-and-plan.md).

---

## Features

### Billing
- Restaurant profile with GSTIN and FSSAI details
- Menu management (categories, items, variants, GST rate per item, availability)
- Tables for dine-in, plus takeaway and delivery orders
- KOT (kitchen order tickets)
- Bills with GST breakdown and invoice numbering
- Payments: cash, UPI, card, and split payments
- Thermal printer output for bills and KOT
- Owner-configured offers and manual discounts at bill time
- Staff roles: owner, manager, cashier, waiter
- Daily sales reports
- **Customer records:** a guest's mobile number on an order creates (or finds) their customer record, so every order, visit and dish is remembered
- **Insights:** most ordered dishes and most frequent returning customers, for the last 7, 30 or 90 days or all time

### WhatsApp chatbot
- Answers guest questions about current offers
- Checks table availability for a date, time, and party size
- Looks up and sends bills
- Creates dine-out bookings
- Replies in the guest's language (multilingual through `gpt-4.1-mini`)
- Does **not** take orders
- Hands off to the owner when it cannot answer

### Dine-out booking
- Opening hours, slot length, and table capacity set by the owner
- Booking statuses: requested, confirmed, seated, completed, no-show, cancelled
- Confirmation and reminder messages

### Customer retention
- RFM scoring (recency, frequency, monetary value) from billing data
- Segments: new, regular, at-risk, lost, VIP (thresholds set by the owner)
- Campaign rules: segment, trigger, message template, and mode
- Each rule is **automatic** or **needs approval**
- Approval queue for pending messages
- Opt-out handling

> Messaging provider (WhatsApp Business API) is not chosen yet. The messaging layer is built behind an interface so a provider can be added later.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.13, FastAPI (async), SQLAlchemy (async), asyncpg, Alembic, APScheduler |
| Frontend | React, Vite |
| Database | PostgreSQL 16 |
| Chatbot | OpenAI `gpt-4.1-mini` with tool calling |
| Local run | Docker and Docker Compose |

---

## Project Structure

```
Restaurant-Management-System/
├── plans/                          # Discussion notes and plan
├── src/restaurant_management_system/
│   ├── config.py                   # Settings class (reads .env)
│   └── main.py                     # FastAPI app
├── frontend/                       # React app (Vite)
├── requirements-backend.txt        # Backend libraries
├── requirements-frontend.txt       # Frontend libraries
├── Dockerfile.backend
├── Dockerfile.frontend
├── docker-compose.yml
├── .env.example                    # Template for .env
└── README.md
```

---

## Setup

### Prerequisites
- Python 3.13
- Docker Desktop (for the database and local containers)
- Node.js 22+ (only if you run the frontend outside Docker)
- Git

### 1. Clone the repository

```bash
git clone <your-repository-url>
cd Restaurant-Management-System
```

### 2. Create the environment file

Copy the template and fill in the values:

```bash
cp .env.example .env
```

Set at least:
- `JWT_SECRET_KEY`: a long random string
- `OPENAI_API_KEY`: needed for the chatbot

Never commit `.env`.

### 3. Create the virtual environment (project-local only)

The virtual environment lives in `.venv/` inside this repository. Do not install packages globally.

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-backend.txt
```

**macOS / Linux:**

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-backend.txt
```

If you use `uv`, you can install into the same venv without activating it:

```bash
uv pip install --python .venv/Scripts/python.exe -r requirements-backend.txt   # Windows
uv pip install --python .venv/bin/python -r requirements-backend.txt           # macOS / Linux
```

### 4. Start the stack with Docker

```bash
docker compose up --build
```

This starts three services:

| Service | URL |
|---|---|
| Backend (FastAPI) | http://localhost:8000 (change with `BACKEND_PORT` in `.env` if the port is taken) |
| API docs (Swagger) | http://localhost:8000/docs |
| Frontend (Vite) | http://localhost:5173 |
| PostgreSQL | localhost:5432 (user `postgres`, password `postgres`, database `restaurant`) |

Stop everything with `docker compose down`. To also delete the database volume, use `docker compose down -v`.

### 5. Run the backend without Docker (optional)

Start PostgreSQL first (for example, `docker compose up db`), then:

```bash
# from the repository root, with .venv activated
set PYTHONPATH=src            # PowerShell: $env:PYTHONPATH = "src"
uvicorn restaurant_management_system.main:app --reload --port 8000
```

On macOS / Linux use `export PYTHONPATH=src`.

Check that it works:

```bash
curl http://localhost:8000/health
# {"status":"ok","environment":"development"}
```

---

## First Run

1. Start the stack (`docker compose up --build`). The backend applies database migrations on startup.
2. Open http://localhost:5173. On a fresh database it shows **Set up your restaurant**: create the owner account.
3. Open **Billing → Menu & tables**: add categories, menu items (price excluding GST, plus GST rate) and tables.
4. Open **Billing → Orders**: tap a free table, tap menu items, **Send to kitchen**, **Generate bill**, **Take payment**, **Print receipt**.

Roles (an owner adds staff through `POST /api/auth/users`; a staff screen is not built yet):

| Role | Can do |
|---|---|
| owner, manager | Everything, including menu, tables, cancelling orders, customers, insights and reports |
| cashier | Take orders, generate bills, take payments |
| waiter | Take orders and send them to the kitchen |

### Customers and insights
- On any order, enter the guest's 10-digit mobile number (and name if you have it). Formats like `+91 98765 43210` are accepted and saved as `9876543210`. The same number always maps to the same customer.
- Typing a known number shows **Returning customer, N visits** immediately.
- A **visit** is one billed order. Open and cancelled orders do not count.
- **Billing → Customers** (owner and manager): search by name or number, open a guest to see their spend, favourite dishes and every past order.
- **Billing → Insights** (owner and manager): *Most ordered dishes* (quantity, orders, sales before GST) and *Most frequent customers* (visits, spend, last visit). Customers tie-break on spend.
- Waiters and cashiers can attach a customer and see only name and visit count. They cannot see spend or history.
- Only billed orders count towards dish rankings. Dishes are counted under the name they were sold as.

API: `GET /api/customers`, `GET /api/customers/{id}`, `GET /api/customers/lookup?phone=`, `PUT /api/billing/orders/{id}/customer`, `GET /api/reports/top-dishes?days=&limit=`, `GET /api/reports/top-customers?days=&limit=`. Full docs at `/docs`.

### Billing rules
- Menu prices are **GST-exclusive**. Tax is split evenly into CGST and SGST (intrastate supply, Delhi).
- A discount is taken off the subtotal before tax, and tax is reduced in proportion.
- The total is rounded to the nearest rupee and the difference is shown as **Round off**.
- Item name, price and GST rate are copied onto the order, so later menu edits never change an existing order.
- Receipts and kitchen tickets are plain text at 42 characters wide (3-inch thermal printers). The browser **Print** button prints just the receipt.
- "Today" in reports and printed times use `TIMEZONE` (default `Asia/Kolkata`).

---

## Database Migrations

```bash
# apply all migrations (Docker does this automatically on start)
python -m alembic upgrade head

# after changing a model
python -m alembic revision --autogenerate -m "describe the change"
```

The migration commands read `DATABASE_URL` from `.env`. When running them from your machine against the Docker database, use host `localhost`.

---

## Configuration

All configuration is read from `.env` through the `Settings` class in `src/restaurant_management_system/config.py`. Code must not read environment variables directly. To add a new setting:

1. Add a typed field to `Settings`.
2. Add the variable to `.env.example`.
3. Read it with `get_settings()`.

| Variable | Default | Purpose |
|---|---|---|
| `ENVIRONMENT` | `development` | Environment name shown by `/health` |
| `APP_NAME` | `Restaurant Management System` | API title |
| `TIMEZONE` | `Asia/Kolkata` | Timezone for report days and printed times |
| `BACKEND_PORT` | `8000` | Host port for the backend container |
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/restaurant` | Async database connection |
| `JWT_SECRET_KEY` | none (required) | Signs login tokens |
| `JWT_ALGORITHM` | `HS256` | Token signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `720` | Login session length |
| `OPENAI_API_KEY` | empty | Key for the chatbot |
| `OPENAI_MODEL` | `gpt-4.1-mini` | Chatbot model |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | Frontend origins allowed to call the API |

---

## Development Rules

1. **Async everywhere.** Route handlers, database access, HTTP calls, and LLM calls use `async` / `await`. Do not add blocking I/O to request paths.
2. **Settings through `config.py` only.** Add new environment values to `Settings` and `.env.example`.
3. **Separate dependency files.** Backend packages go in `requirements-backend.txt`. Frontend packages go in `requirements-frontend.txt` and `frontend/package.json`.
4. **One venv.** Use `.venv/` in the repo root.
5. **Run tests:** see [Testing](#testing).

---

## Testing

**Backend** (pytest, async, runs in the project `.venv`):

```bash
python -m pytest
```

**Frontend** (Vitest + Testing Library, jsdom):

```bash
cd frontend
npm install
npm test
```

**Live check** (with the stack running via `docker compose up -d`):

```bash
curl http://localhost:8000/health        # use your BACKEND_PORT
curl -I http://localhost:5173/
```

---

## Build Order and Status

| Stage | Scope | Status |
|---|---|---|
| 0 | Project setup, Docker, config, health endpoint | Done |
| 1 | Billing: menu, tables, orders, KOT, bills, payments, printing | Done (see notes below) |
| 2 | WhatsApp chatbot: offers, bills, availability (tool calling) | Planned |
| 3 | Dine-out booking | Planned |
| 4 | Customer retention: RFM, campaigns, approval queue | Planned |

Full plan and decisions: [`plans/01-discussion-and-plan.md`](plans/01-discussion-and-plan.md).

---

## Out of Scope (for now)

- Customer orders through WhatsApp
- Cities other than Delhi
- Choosing a WhatsApp provider (deferred)
- Cloud hosting (local Docker only)

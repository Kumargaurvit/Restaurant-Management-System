# Restaurant Management System

A billing, WhatsApp chatbot, dine-out booking, and customer retention system for small and medium restaurants. The first market is **metro cities, starting with Delhi**.

Planning documents are in [`plans/`](plans/01-discussion-and-plan.md).

---

## Features

### Billing
- Restaurant name (set at registration, owner can rename), receipt details (address, phone, GSTIN, FSSAI, footer) printed on every receipt, and an optional **logo** shown in the app header and on the bill preview
- Menu management: add, edit, move, delete and mark unavailable (categories, items, GST rate per item), and edit or deactivate tables
- **Sizes** (for example Half / Full) with their own prices, and optional **stock counts** that go down as items are ordered, with a sold-out state and low-stock warnings
- Tables for dine-in, plus takeaway and delivery orders
- KOT (kitchen order tickets)
- Bills with GST breakdown and invoice numbering
- Payments: cash, UPI, card, and split payments
- Thermal-printer-width (42 character) bills and KOT, printed from the browser
- **Send the bill to the guest on WhatsApp** from the bill screen
- Owner-configured offers, applied at bill time with one tap, plus manual discounts
- Staff management: add staff, change roles, deactivate, reset passwords (owner)
- Staff roles: owner, manager, cashier, waiter
- Daily sales reports
- **Customer records:** a guest's mobile number on an order creates (or finds) their customer record, so every order, visit and dish is remembered
- **Insights:** most ordered dishes and most frequent returning customers, for the last 7, 30 or 90 days or all time

### WhatsApp chatbot
- Answers guest questions about current offers, using only the offers the owner has set up (it never invents a discount)
- Answers "where are you, what are your timings, are you open?" from the restaurant details and booking hours
- Says whether there is room **right now**, or which booking slots are free on a given day (using the Bookings opening hours and existing reservations)
- **Requests a table booking** for the guest. It starts as *requested*; when staff confirm it in Bookings, the guest gets a WhatsApp message
- Shows a guest their own upcoming bookings
- Shows a guest their own recent bills and sends a receipt (only ever the bills for the guest's own number)
- Replies in the guest's language (multilingual through `gpt-4.1-mini` with tool calling)
- Does **not** take food orders, and cannot change or cancel a booking; it hands those to a person
- A guest can hold at most 3 upcoming bookings through the bot; more needs a person
- Limits each guest to 30 messages an hour (`CHAT_MAX_MESSAGES_PER_HOUR`), so a flood costs nothing
- Hands the chat to a person when it cannot answer or the guest is upset; these show in a "needs a person" queue
- Owner screens: **Offers**, **Conversations**, and a **Test chat** to try the bot without WhatsApp

### Dine-out booking
- Opening hours, slot length, party-size limit, booking window and reminder lead time set by the owner
- Availability is worked out from the tables and the bookings that overlap each slot
- Booking statuses: requested, confirmed, seated, completed, no-show, cancelled
- Confirmation, cancellation and reminder messages on WhatsApp
- Guests can book through the WhatsApp bot as well as staff in the app

### Customer retention
- RFM scoring (recency, frequency, monetary value) from billing data
- Segments: new, regular, at-risk, lost (thresholds set by the owner)
- Campaign rules: segment, trigger, message template, and mode
- Each rule is **automatic** or **needs approval**
- Approval queue for pending messages
- Opt-out handling (STOP / START replies and a staff toggle)
- A results report per rule: sent, waiting, rejected, opted out, replied, returned

### Platform
- JWT login with roles, async API, PostgreSQL with migrations, background jobs for reminders and campaigns
- Structured logging: readable text or one JSON object per line (`LOG_FORMAT=json`). Every response carries an `X-Request-ID`, and request logs never include query strings (they can hold phone numbers)

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
├── plans/                          # Discussion notes, plan and progress log
├── src/restaurant_management_system/
│   ├── main.py                     # FastAPI app, request logging, scheduler start-up
│   ├── config.py                   # Settings class (reads .env)
│   ├── logging_config.py           # Text / JSON log formats
│   ├── scheduler.py                # Booking reminders and automatic campaigns
│   ├── auth/                       # Login, roles, staff management
│   ├── billing/                    # Menu, sizes, stock, orders, KOT, bills, payments, receipts
│   ├── customers/                  # Customer records, insights, marketing opt-out
│   ├── booking/                    # Opening hours, slots, bookings, reminders
│   ├── retention/                  # Segments, campaign rules, approval queue, report
│   ├── chatbot/                    # Model client, tools, offers, conversations, hand-off
│   ├── messaging/                  # WhatsApp provider interface, message log, inbound webhook
│   ├── restaurant/                 # Name, receipt details, logo
│   └── db/                         # Database base class and sessions
├── alembic/                        # Database migrations
├── tests/                          # Backend tests (pytest)
├── frontend/                       # React app (Vite) and its tests (Vitest)
├── e2e/                            # Real-browser check of the whole app
├── requirements-backend.txt        # Backend libraries
├── requirements-frontend.txt       # Frontend libraries
├── Dockerfile.backend
├── Dockerfile.frontend
├── docker-compose.yml
├── docker-compose.e2e.yml          # Isolated stack for the browser check
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

> **Upgrading an older local database:** the migrations were reorganised when the chatbot and booking work were combined. A local database created before that (it reports a revision such as `6ee78296e767` or `9120eff7227e`) cannot be upgraded. Recreate it with `docker compose down -v` and `docker compose up -d` (this deletes local data). Databases created from the current `main` just upgrade automatically.

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
4. Open **Settings**: add your address, GSTIN, FSSAI number and a logo under *Receipt details*, and add staff.
5. Open **Billing → Orders**: tap a free table, enter the guest's number and name, tap menu items, **Send to kitchen**, **Generate bill**, **Take payment**, then **Print receipt** or **Send on WhatsApp**.
6. Open **Bookings → Hours & slots** to set opening hours, and **WhatsApp Bot → Offers** to add offers.

Roles (the owner adds and manages staff in **Settings → Staff**):

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
- "Today" in reports and printed times use `TIMEZONE` (default `Asia/Kolkata`). A bill made at 00:15 in Delhi belongs to the new day, even though it is still the previous day in UTC.

### Sizes and stock
- **Sizes:** in **Billing → Menu & tables**, press *Sizes of ...* on an item to add sizes such as Half and Full, each with its own price. Tax still comes from the item. Once an item has sizes it must be ordered by size, and the order screen shows one button per size. Names and prices are copied onto the order, so deleting or repricing a size never changes a past bill.
- **Stock:** give an item a stock number (or leave it empty if you don't count it). Adding it to an order takes stock; reducing a line, removing it, or cancelling the order puts it back. At zero the item shows **Sold out** and cannot be ordered. Stock is shared across an item's sizes. The take is atomic, so two waiters cannot both sell the last portion. Items with 5 or fewer left show a low-stock warning. Stock is only touched by orders, and it is set (or cleared to stop counting) by editing the item.

### Sending a bill on WhatsApp
On a bill, **Send on WhatsApp** uses the guest's number from the order (you can change it). The receipt is sent as a message and logged. A bill is a service message, so a guest who opted out of marketing still receives it. Owners, managers and cashiers can send bills.

---

## WhatsApp Bot

### Turning the bot on
1. Put your OpenAI key in `.env`: `OPENAI_API_KEY=sk-...` (model defaults to `gpt-4.1-mini`), then restart the backend.
2. Open **WhatsApp Bot → Test chat** and talk to it as a guest. Nothing is sent to WhatsApp from there.
3. Without a key the bot is "off": every guest message gets a polite fallback and is flagged for a person.

### Offers
Open **WhatsApp Bot → Offers**. The bot only quotes offers listed here. Each offer has a title, details, an optional discount percentage, and an optional start and end time.
For a discount that changes over time (for example 15% for the next 2 hours, then 10%), create **one offer per period**: the first ends in 2 hours, the second starts then. The bot will tell a guest about both. Pause an offer to hide it without deleting it.
Percentage offers also appear as **Apply ...** buttons next to the discount box when billing.

### Conversations and hand-off
**WhatsApp Bot → Conversations** lists every guest chat, with the ones that need a person first. Open one to read the thread and why the bot handed it over, then **Mark as handled**. Replying from the app is not built yet: reply to the guest on WhatsApp.

### Connecting real WhatsApp (later)
The WhatsApp provider is not chosen yet. All outbound messages (bot replies, booking confirmations and reminders, retention campaigns) go through one interface, `messaging/provider.py`, and today only a `log` provider that records messages exists. There is **one inbound entry point**:

```
POST /api/messaging/inbound
X-Webhook-Secret: <WHATSAPP_WEBHOOK_SECRET>
{"phone": "9810000001", "text": "is there space for 2?"}
```

It is **disabled** (401) until `WHATSAPP_WEBHOOK_SECRET` is set in `.env`. For every message it:
1. logs it in the `messages` table (the retention report counts guest replies to campaigns from this log),
2. handles `STOP` / `START` as a marketing opt-out / opt-in, without involving the bot,
3. otherwise sends it to the chatbot and sends the reply back through the provider (also logged).

Adapting a provider's own payload format to this one is a small piece of glue code. `OWNER_CONTACT` (optional) is shown to guests when the bot hands a chat to a person.

### Limits and safety
- Each guest can send up to `CHAT_MAX_MESSAGES_PER_HOUR` (default 30) messages an hour. Past that they get a polite notice, the model is not called and nothing is stored. Set it to `0` for no limit.
- Replies only use tool results. The bot cannot take food orders or change or cancel a booking, and hands those to a person.

### What the bot can use
`get_restaurant_info`, `get_active_offers`, `check_table_availability`, `create_booking_request`, `get_my_bookings`, `get_my_recent_bills`, `get_bill_receipt`, `request_human_handoff`. Every tool is scoped to the guest's own phone number taken from the webhook, never from the model, so a guest cannot read another guest's data.

---

## Bookings

Open **Bookings**. Staff can book a table for a guest (name, mobile number, party size, date and a free time), and guests can request one through the WhatsApp bot.

- **Hours & slots** (owner and manager) sets opening and closing time, slot length, the largest party, how many days ahead guests can book, and how many hours before a booking the reminder goes out. Defaults: 11:00 to 23:00, 90-minute slots, parties up to 12, 30 days ahead, reminder 3 hours before.
- A booking holds one table for its slot. Parties are packed onto tables smallest-fit-first, and seats are not pooled across tables.
- **Status flow:** requested → confirmed → seated → completed, with no-show and cancelled as other endings. Bookings made by staff or the bot start as *requested*. **Confirming** (or cancelling) sends the guest a WhatsApp message.
- **Reminders** go to guests with a confirmed booking that starts within the reminder window. They run every 10 minutes while `SCHEDULER_ENABLED=true`, or on demand with `POST /api/bookings/send-reminders`.
- Booking and bill messages are service messages: the marketing opt-out does not stop them.

---

## Retention

Open **Retention** to win guests back, using the billing data.

- **Segments:** each customer gets recency, frequency and spend scores from 1 to 5, and falls into one segment: *lost* (no visit for `lost_days`, default 90), *at risk* (`at_risk_days`, default 45), *new*, or *regular*, checked in that order. The thresholds are set by the owner. Customers who have never been billed are not segmented.
- **Campaign rules:** a rule picks a segment, a message template and a mode, plus a cooldown (default 30 days) so one guest is not messaged twice in that time. Templates can use `{name}`, `{visits}`, `{days_since_visit}` and `{restaurant}`. Every campaign message ends with "Reply STOP to opt out."
- **Automatic** rules are sent by a daily job at 11:00 restaurant time. **Approval** rules queue their messages when the owner presses **Run rules now**; the owner then approves or rejects each one in the **Approval queue**.
- **Opt-out:** a guest who replies `STOP` is opted out of campaigns (`START` opts back in), and staff can toggle it on the Customers screen. It is checked when a message is queued, sent and approved.
- **Results:** per rule, how many messages were sent, are waiting, were rejected or skipped for opt-out, how many guests replied, and how many came back and were billed after the message. "Delivered" is not tracked, because it depends on the WhatsApp provider.

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
| `BCRYPT_ROUNDS` | `12` | Password hashing cost (tests use a low value) |
| `OPENAI_API_KEY` | empty | Key for the chatbot. Empty means the bot only sends the fallback reply |
| `OPENAI_MODEL` | `gpt-4.1-mini` | Chatbot model |
| `WHATSAPP_PROVIDER` | `log` | Outbound WhatsApp provider (only `log` exists) |
| `WHATSAPP_WEBHOOK_SECRET` | empty | Shared secret for `POST /api/messaging/inbound`. Empty disables it |
| `OWNER_CONTACT` | empty | Shown to guests when the bot hands a chat to a person |
| `SCHEDULER_ENABLED` | `true` | Run booking reminders and automatic retention campaigns |
| `CHAT_HISTORY_MESSAGES` | `12` | Recent messages sent to the model for context |
| `CHAT_MAX_TOOL_ROUNDS` | `4` | Most tool-calling rounds per guest message |
| `CHAT_MAX_MESSAGES_PER_HOUR` | `30` | Most messages one guest may send the bot per hour (`0` = no limit) |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_FORMAT` | `text` | `text` for people, `json` for log tools |
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

**End-to-end** (a real browser against a real database; see [`e2e/README.md`](e2e/README.md)):

```bash
docker compose -p rmse2e -f docker-compose.yml -f docker-compose.e2e.yml up -d --build
cd e2e && npm install && npm test && npm run layout && cd ..
docker compose -p rmse2e -f docker-compose.yml -f docker-compose.e2e.yml down -v
```

It runs in its own isolated stack and never touches your normal database.

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
| 1 | Billing: menu, sizes, stock, tables, orders, KOT, bills, payments, receipts | Done |
| 2 | WhatsApp chatbot: offers, bills, availability and bookings (tool calling) | Done, except a real WhatsApp provider |
| 3 | Dine-out booking | Done |
| 4 | Customer retention: RFM, campaigns, approval queue | Done |

Full plan and decisions: [`plans/01-discussion-and-plan.md`](plans/01-discussion-and-plan.md).

---

## Out of Scope (for now)

- Customer orders through WhatsApp
- Cities other than Delhi
- Choosing a WhatsApp provider (deferred). The bot works through the test chat and the webhook only.
- Food orders through the bot, and changing or cancelling a booking through the bot
- Card and UPI payment-gateway integration (payments are recorded by hand)
- Direct thermal-printer (ESC/POS) control: receipts print through the browser
- Message "delivered" tracking (depends on the WhatsApp provider)
- Replying to a guest from the app (reply on WhatsApp)
- Stock alerts by message, purchase orders and ingredient-level inventory
- Cloud hosting (local Docker only)

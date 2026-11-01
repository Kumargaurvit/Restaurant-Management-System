# Restaurant Management System: Discussion and Plan

**Date:** 2026-10-22
**Team:** 2 developers
**Target:** Working version by Friday 2026-10-23 (evening), then enhancements
**Source research:** "Billing Automation and Customer Retention Strategies in Indian Small-to-Medium Restaurants" (PDF)

---

## 1. Product Summary

A restaurant management system for small and medium restaurants in India, starting with **metro cities, Delhi only**. It combines:

1. **Billing:** a full billing and POS system (everything the restaurant needs to bill a guest).
2. **WhatsApp chatbot:** answers guest questions about offers, bills, and table availability, and handles dine-out booking. It does **not** take orders.
3. **Booking:** dine-out table reservations.
4. **Customer retention:** RFM-based (recency, frequency, monetary) marketing messages sent over WhatsApp, either automatically or after owner approval.

The core thesis from the PDF: restaurants generate billing data but rarely use it. Embedding retention and messaging inside the billing tool solves the cold-start data problem.

---

## 2. Decisions Made

| # | Topic | Decision |
|---|---|---|
| 1 | Geography | Metro cities. Delhi only for now. |
| 2 | Billing scope | **Everything**: dine-in, takeaway, delivery, GST invoicing, KOT, printing, payment modes, inventory where needed for billing. |
| 3 | Chatbot scope | **No customer orders.** The bot handles: offers and discounts, bill lookup and sending, marketing messages, and dine-out booking. |
| 4 | Booking | **Yes.** Dine-out table booking is in scope. |
| 5 | Retention messages | **Both modes.** The owner chooses per rule whether a message sends automatically or waits for approval. |
| 6 | Build order | Billing → Chatbot → Booking → Retention (the order suggested in the PDF analysis). |
| 7 | Tech stack | Backend: Python (FastAPI, async). Frontend: React (Vite). Database: PostgreSQL. Chatbot LLM: OpenAI `gpt-4.1-mini` with tool calling. Run locally with Docker. |
| 8 | Chatbot languages | Multilingual. Handled by `gpt-4.1-mini`; no separate translation layer. |
| 9 | Docker layout | Separate requirement files and Dockerfiles per side: `requirements-backend.txt`, `requirements-frontend.txt`, `Dockerfile.backend`, `Dockerfile.frontend`. |
| 10 | Environment config | All settings come from `.env` through `Settings` in `src/restaurant_management_system/config.py`. |
| 11 | Concurrency | Everything is `async`: routes, database access (SQLAlchemy async + asyncpg), HTTP calls (httpx), and LLM calls. |
| 12 | Virtual environment | Single project venv at `.venv/` in the repo root. No global installs. |

### Chatbot behavior examples (illustrative only)

These show the kind of questions the bot answers. They are **not** the full feature list, and the discount example below is only an example of the format, not a fixed rule:

- "Is there space for 2 tonight?" → the bot checks availability and answers yes or no.
- "Is any discount available?" → the bot returns the current offer from the owner's configured offers.

The owner configures offers. The bot does not hard-code discount values.

---

## 3. Explicitly Skipped (for now)

| Item | Reason |
|---|---|
| Choosing a WhatsApp Business API provider (Gupshup, Wati, respond.io, etc.) | Deferred by decision. Keep the messaging layer behind an interface so a provider can be plugged in later. |
| Customer orders through WhatsApp | Out of scope for the bot. |
| Cities outside Delhi | Not in scope yet. |
| Hosting beyond local Docker | Local Docker only for now. |
| Enhancements after the first working version | Planned after Friday. |

---

## 4. Assumptions (to confirm)

These came from the discussion or the PDF, and were not explicitly confirmed:

- **End users of the bot are restaurant guests.** The paying customer is the restaurant owner.
- **Payment modes:** cash, UPI, card. Payment gateway integration is not decided.
- **Printing:** thermal printer support for bills and KOT. Exact printer model not decided.
- **Pricing:** the PDF suggests ₹1,000–3,000/month. Not yet decided.
- **WhatsApp messages** are sent through a provider behind an abstraction, so the provider can change without touching business logic.
- **Data privacy:** guest phone numbers are personal data. Consent and opt-out handling are required for marketing messages. Compliance with the DPDP Act 2023 should be checked before any real customer data is stored.

---

## 5. Feature Scope

Items marked *(suggested)* were added during planning and were not discussed explicitly. Remove any you don't want.

### 5.1 Billing (build first)
- Restaurant profile: name, address, GSTIN, FSSAI number, logo.
- Menu management: categories, items, variants, prices, GST rate per item, availability toggle.
- Tables and floor plan (dine-in).
- Orders for dine-in, takeaway, and delivery.
- KOT (kitchen order tickets) generation.
- Bill generation with GST breakdown and invoice numbering.
- Payments: cash, UPI, card. Split payments.
- Printing: thermal printer output for bills and KOT.
- Discounts applied at bill time (manual and owner-configured offers).
- Staff accounts with roles (owner, manager, cashier, waiter) *(suggested)*.
- Daily sales reports *(suggested)*.
- Customer records created automatically from bills (name, phone, visits, spend) *(suggested)*.

### 5.2 WhatsApp Chatbot (build second)
- Receives guest messages through the messaging provider (provider decided later).
- Uses `gpt-4.1-mini` with tool calling. Tools include:
  - `check_table_availability(date, time, party_size)`
  - `get_active_offers()`
  - `get_bill(bill_id or phone)` and send bill
  - `create_booking(...)`
- Replies in the guest's language.
- Hands off to a human owner contact when it cannot answer (fallback message).
- Conversation log stored per guest *(suggested)*.

### 5.3 Dine-Out Booking (build third)
- Owner sets opening hours, slot length, and table capacity.
- Guest books by name, phone, date, time, party size (through the bot or the web app).
- Booking statuses: requested, confirmed, seated, completed, no-show, cancelled.
- Booking confirmation and reminder messages.
- Availability calculated from tables, slots, and existing bookings.

### 5.4 Customer Retention (build fourth)
- RFM scoring for each customer from billing data (recency, frequency, monetary value).
- Segments (for example: new, regular, at-risk, lost, VIP). Exact thresholds set by the owner.
- Campaign rules: segment + trigger + message template + mode (automatic or approval).
- Approval queue: owner reviews and approves each message before sending when approval mode is on.
- Marketing templates and opt-out handling.
- Basic campaign report: sent, delivered, replied, visits after campaign *(suggested)*.

### 5.5 Platform (cross-cutting)
- JWT authentication for web app users.
- Role-based access control.
- Async API with FastAPI.
- PostgreSQL with SQLAlchemy (async) and Alembic migrations.
- Background jobs (APScheduler) for automatic retention sends and reminders *(suggested)*.
- Structured logging *(suggested)*.
- Settings loaded from `.env` through `Settings` in `config.py`.

---

## 6. Architecture (planned)

```
Browser (React)  ──HTTP/JSON──►  FastAPI backend (async)  ──►  PostgreSQL
                                   │       ▲
                                   │       │ webhook (inbound messages)
                                   │       │
                                   ▼       │
                            OpenAI gpt-4.1-mini        WhatsApp provider (TBD)
                            (tool calling)             ◄── outbound messages
                                   │
                            APScheduler jobs (retention, reminders)
```

Repo layout (planned):

```
Restaurant-Management-System/
├── plans/                          # this folder
├── src/restaurant_management_system/
│   ├── config.py                   # Settings (reads .env)
│   ├── main.py                     # FastAPI app factory
│   ├── billing/                    # menu, orders, bills, payments, KOT
│   ├── chatbot/                    # LLM client, tools, conversation handling
│   ├── booking/                    # tables, slots, reservations
│   ├── retention/                  # RFM, campaigns, approval queue
│   ├── messaging/                  # WhatsApp provider interface
│   └── db/                         # models, sessions, migrations
├── frontend/                       # React app (Vite)
├── requirements-backend.txt
├── requirements-frontend.txt
├── Dockerfile.backend
├── Dockerfile.frontend
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 7. Standing Rules

1. **Async everywhere.** Route handlers, DB access, HTTP and LLM calls are all `async`. No blocking I/O in request paths.
2. **Config only through `Settings`.** Any new environment value is added to `Settings` in `config.py` and to `.env.example`. Code does not read `os.environ` directly.
3. **Separate requirement files.** Backend libraries go in `requirements-backend.txt`. Frontend libraries go in `requirements-frontend.txt`.
4. **One venv, inside the project.** Use `.venv/` in the repo root only.
5. **Docker for local runs.** Backend and frontend each have their own Dockerfile.

---

## 8. Timeline and Honesty Check

The target is to finish everything in discussion by Friday. Billing alone, plus a working chatbot, booking, and retention, is a large scope for two developers in about one day. Realistic expectations:

- **By Friday:** project setup, Docker, database, authentication, the core billing flow (menu → order → bill → payment → print), and a basic chatbot that answers offers and bill questions.
- **After Friday (enhancements):** dine-out booking, retention with RFM and approvals, full GST and printing polish, and any remaining chatbot tools.

Scope for Friday should be confirmed against this order. Anything not finished moves to the enhancement list rather than being rushed.

---

## 9. Open Questions

- Which WhatsApp provider to use (deferred by decision).
- Payment gateway for UPI and card, if any (cash-only is possible for the first version).
- Pricing model and first-pilot restaurant in Delhi.
- Printer model used by pilot restaurants.
- Whether the owner or staff use the bot for internal queries.

---

## 10. Progress Log

### 2026-10-22: Stage 0 and Stage 1 (billing)

**Done**
- Project setup: Docker (backend, frontend, PostgreSQL), `Settings` config, Alembic migrations, test suites.
- Authentication: first-owner setup, JWT login, roles (owner, manager, cashier, waiter).
- Billing backend: menu, tables, dine-in/takeaway/delivery orders, KOT, GST bills, split payments, plain-text receipts and kitchen tickets, daily sales report.
- Billing frontend: login/setup, tables and order taking, kitchen ticket, bill, payment, receipt printing, menu and table setup, reports.

**Decisions made during the build** (change any of these if wrong)
- Menu prices are GST-exclusive; CGST and SGST split 50/50 (Delhi, intrastate).
- Discounts are a rupee amount taken off the subtotal before tax; totals round to the nearest rupee.
- One restaurant per deployment (no multi-tenant support yet).
- A table can have only one open order at a time.
- Overpayment is rejected (no change handling yet).
- Invoice numbers are `INV-<year>-<6 digit counter>`; the counter does not reset each year.
- Receipt printing uses plain text through the browser's print dialog. Direct ESC/POS printer support is not built.

**Added after the first Stage 1 build:** customer records, per-customer order history and favourite dishes, and the Insights reports (see the 2026-10-22 customer entry below).

**Not built yet (still in Stage 1 scope, listed so nothing is forgotten)**
- Staff management screen (staff can only be created through the API today).
- Restaurant profile (name, GSTIN, FSSAI, address) printed on receipts. Receipts currently say only "TAX INVOICE".
- Inventory, payment gateway integration, and editing or deleting categories, items and tables.

**Next:** Stage 2 (WhatsApp chatbot), after the missing Stage 1 items above are decided.

### 2026-10-22: Customer data and insights (requested by the owner)

**Goal:** save everything about customers and their orders so the owner can see which dishes sell most and which customers return most.

**Done**
- `customers` table (unique 10-digit mobile number, optional name) and `orders.customer_id`. Migration `06814ee5a29f`.
- A guest is attached to an order by mobile number, when the order is created (takeaway, delivery) or any time before billing (dine-in).
- Reports: most ordered dishes and most frequent customers, with a period filter. Customer list, search, and per-customer history with favourite dishes.
- Staff screen shows a returning-customer badge while taking an order.

**Decisions** (change if wrong)
- A customer is identified by mobile number only. Non-Indian numbers are rejected for now.
- A **visit** is one billed order (paid or unpaid). Open and cancelled orders do not count.
- Customer lists, spend and history are visible to owner and manager only. Waiters and cashiers see name and visit count.
- A guest's name is saved the first time it is given and is not overwritten by later orders.
- Orders without a mobile number are still billed and counted in dish rankings, but not tied to a customer.

**Notes for later stages**
- Stage 4 (retention) and Stage 2 (chatbot) will reuse this `customers` table, with the mobile number as the WhatsApp number.
- Mobile numbers are personal data. Consent and opt-out for marketing messages must be added before any WhatsApp campaign (DPDP Act 2023).
- Orders created before this change have no customer link and cannot be backfilled.

### 2026-10-22: Stage 3 (bookings) and Stage 4 (retention)

Stage 2 (the chatbot) is **not built yet**. Bookings and retention were built first; both work from the web app.

**Done**
- `messaging/`: a `MessageProvider` interface (default `log` provider records messages without sending), a `messages` log table, and `POST /api/messaging/inbound` for the provider webhook (needs `WHATSAPP_WEBHOOK_SECRET`). It logs guest replies and handles STOP / START.
- Bookings: owner-set opening hours, slot length, party limit, booking window and reminder lead time. Availability is checked against active tables and the bookings that overlap the slot. Status flow requested → confirmed → seated → completed, with no-show and cancelled. Confirmation, cancellation and reminder messages. Reminders run every 10 minutes (APScheduler) or on demand.
- Retention: RFM scores (1–5) and segments (regular, new, at risk, lost) with owner-set thresholds. Campaign rules (segment, template, automatic or approval, cooldown). Approval queue. Results report (sent, waiting, rejected, opted out, replied, returned).
- Marketing opt-out: customer fields, staff toggle on the Customers screen, STOP / START replies through the webhook, and a check when a message is queued, sent or approved.
- Web app: the Bookings and Retention tabs are live. Migration `b2d4f6a8c0e1`.

**Decisions** (change if wrong)
- A booking holds one table for the slot. Parties are packed onto tables smallest-fit-first, and seats are not pooled across tables. No table number is stored on the booking.
- Staff-created bookings start as *requested*; confirming one sends the guest a message.
- Booking and bill messages are service messages and ignore the marketing opt-out. Campaign messages never do.
- Segment order: lost, then at risk, then new, then regular. Customers with no bill are not segmented.
- Every campaign message ends with "Reply STOP to opt out."
- A rule messages a guest at most once per cooldown (30 days by default), including rejected ones, so a rejected message is not re-queued the next day.
- Automatic rules run daily at 11:00 (restaurant timezone). Approval rules queue when the owner presses "Run rules now".
- "Delivered" is not tracked: it depends on the provider. Replied and returned are counted instead.
- Offers are not built (they belong to the chatbot stage).

**Next:** Stage 2 (chatbot), which should call `booking.services.create_booking` and `get_provider`, and check `customers.services.can_receive_marketing` before any marketing message.

### 2026-10-22: Restaurant name, new-order forms and bill changes

**Done**
- The restaurant name is asked for when the owner registers, stored in `restaurant_profile` and returned with the signed-in user. The header reads "Restaurant Manager - <name>". The owner can rename it in Settings.
- The name is the first line of the customer bill (above TAX INVOICE). The kitchen ticket keeps its KITCHEN ORDER heading. Booking and campaign messages use the saved name instead of the old `RESTAURANT_NAME` setting, which is removed.
- Order lines show each item's price next to its name. The printed bill already showed quantity x price and the line amount.
- Takeaway and dine-in (new button, or tap a free table) open the same form: contact number and customer name are both required, and the number can be searched to find an existing customer and fill in their name. The server still accepts orders without a customer (delivery, older clients).
- The VIP segment and its thresholds are removed. Migration `c3e5a7b9d1f2` drops the columns and pauses any rule that targeted VIP.


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

### 2026-10-22: Stage 1 completion and Stage 2 (WhatsApp chatbot), branch `ms-phase-2`

**Stage 1 items completed**
- Restaurant profile (name, address, phone, GSTIN with format check, FSSAI, footer) printed on receipts. Migration `9120eff7227e`.
- Edit and delete for menu categories, items and tables. Deleting is blocked when history exists (an ordered item must be marked unavailable, a used table deactivated, a category with items kept), so past orders never break.
- Staff management in Settings (owner): add staff, change role, deactivate and reactivate, reset password. The last active owner cannot be removed and owners cannot demote or deactivate themselves.
- Password hashing cost is now a setting (`BCRYPT_ROUNDS`), which also made the test suite about four times faster.

**Still not built from Stage 1** (decided to defer)
- Inventory and stock tracking.
- Payment gateway integration (UPI and card are recorded manually).
- Direct thermal printer (ESC/POS) support; receipts print through the browser.

**Stage 2 built**
- Offers: owner-configured with optional start and end times, status (active, upcoming, expired, paused), and a one-tap "Apply" at billing. No discount values are hard-coded; time-based discounts are modelled as several offers.
- Chat engine: `gpt-4.1-mini` with tool calling, history of the last 12 messages, up to 4 tool rounds, and a polite fallback (plus hand-off flag) when the model is off, fails or returns nothing.
- Tools: `get_active_offers`, `check_table_availability` (right now), `get_my_recent_bills`, `get_bill_receipt`, `request_human_handoff`. All scoped to the guest's phone from the webhook, verified by tests that deliberately break the scoping.
- Conversations stored per guest, with a "needs a person" queue and Mark as handled.
- Inbound webhook protected by `WEBHOOK_SECRET` (disabled when empty); a console provider stands in for WhatsApp. A **Test chat** screen lets the owner try the bot with no WhatsApp at all.
- Migration `6ee78296e767`.

**Decisions** (change if wrong)
- Table availability means free **right now**. Date and time reservations are Stage 3.
- The bot never takes food orders or reservations; it hands them to a person.
- Guests are identified by their WhatsApp number, the same 10-digit number used for customers.
- Replying to a guest from the app is not built; the owner replies on WhatsApp.
- Guest messages are cut at 1,000 characters.

**Not done in Stage 2**
- A real WhatsApp provider (still undecided) and its payload adapter.
- Rate limiting and per-guest message caps, and OpenAI cost tracking.
- Opening hours are not modelled, so the bot cannot answer "are you open?".
- The bot has never been run against the real OpenAI API, because no key is configured. Everything around the model is tested with a scripted model; the real client is tested against a fake SDK response.

**Next:** Stage 3 (dine-out booking), which also upgrades the bot's availability tool and adds a booking tool.

### 2026-11-01: Merging `main` (bookings, retention, messaging) with our chatbot, branch `ms-phase-2-chatbot-check`

**Comparison.** `main` already held the other developer's work (PR #1, `gk-phase-2-3-build`): bookings, retention, a messaging layer, the restaurant name, and the opt-out. His own notes say "Stage 2 (the chatbot) is **not built yet**". What he called phase 2 is the messaging layer (a `MessageProvider` interface, a `messages` log, and an inbound webhook that only handles STOP and START). That is infrastructure the chatbot needs, not a chatbot: no model, offers, availability, bills or hand-off. So there was no competing chatbot to keep or remove; our chatbot is the chatbot, and his messaging layer stays because bookings and retention depend on it.

**What was kept from `main` unchanged in behaviour:** bookings (settings, slot availability, status flow, reminders), retention (RFM, rules, approval queue, report), the marketing opt-out, the scheduler, restaurant name at registration, the new-order form, all of his tests.

**What was kept from our branch:** chatbot (model tools, offers, conversations, hand-off, test chat), customer insights, staff management, menu and table editing, receipt details, the configurable password-hashing cost.

**What was reconciled**
- **One messaging layer.** Our `messaging/base.py`, `console.py` and `factory.py` were removed in favour of his `messaging/provider.py` (`send(phone, body) -> bool`, `build_provider`, `send_message`).
- **One inbound webhook:** `POST /api/messaging/inbound`. STOP and START are handled exactly as before; every other message is logged, answered by the bot, and the reply is sent through the provider and logged. Our separate `/api/chat/webhook` was removed. Setting names follow his: `WHATSAPP_PROVIDER`, `WHATSAPP_WEBHOOK_SECRET`, `OWNER_CONTACT`, `SCHEDULER_ENABLED`.
- **Restaurant profile.** Both of us had built it. His name API is unchanged (`GET`/`PUT /api/restaurant`, owner renames, his tests rely on it). Our address, phone, GSTIN, FSSAI and footer live at `/api/restaurant/profile` (owner and manager can edit). The receipt prints the name alone as a compact header, and adds the details under it when they are saved.
- **Migrations.** Ours branched from the same parent as his and also created `restaurant_profile`, which would have produced two heads. Our two migrations were deleted and replaced by one on top of his chain: `cf61375cfc10` (receipt detail columns and the chatbot tables). Tested up, down and up again; no drift between models and database.
- **Tests.** His tests were left alone except one expectation: his dashboard test said the WhatsApp Bot was "Stage 2"; it is now live.

**Chatbot upgrades made possible by his booking engine** (his notes said the chatbot should call it)
- `check_table_availability` with a date lists the free booking slots for a party, using his availability rules. Without a date it answers walk-in availability and also respects opening hours and tables held by bookings.
- `create_booking_request` creates a booking with source `whatsapp`, status *requested*. Staff confirm it in Bookings and the guest is messaged by his existing flow. A guest may hold at most 3 upcoming bookings through the bot.
- `get_my_bookings` lists the guest's own upcoming bookings.
- The hand-off shows `OWNER_CONTACT` when it is configured, and the system prompt now carries the restaurant name and today's date so "tomorrow" and "Saturday" resolve correctly.

**Decisions** (change if wrong)
- The bot cannot change or cancel a booking; it hands those to a person.
- Bot replies are service messages, so the marketing opt-out does not stop them. Campaign messages still obey the opt-out as before.
- Guests who book through the bot become customers, because his booking code creates the customer record.

**Heads-up about local databases.**
- A database made from `main` (the other developer's): just run `alembic upgrade head`. It applies `cf61375cfc10` and keeps all data.
- The local database made from our branch **before** this merge has revisions that no longer exist (`9120eff7227e`, `6ee78296e767`) and lacks his bookings, retention and messaging tables, so it cannot be upgraded or stamped into the new chain. Recreate it with `docker compose down -v` then `docker compose up -d` (this deletes the local data).

**Still open:** a real WhatsApp provider; the bot has never run against the real OpenAI API (no key configured); rate limiting and cost tracking; direct replies from the app.

### 2026-11-02: Finishing the plan (branch `ms-phase-4`)

**Starting point.** PR #2 had merged the *backend* for sizes, stock, the logo, sending a bill, the bot's restaurant-info tool, the bot rate limit and structured logging, but with **no database migration and no screens**. A fresh start of `main` would have failed on the menu. Retention (Stage 4) was already built by the other developer, so "what is left" meant finishing everything the audit against this plan had found missing.

**Built**
- **Migration `04b6e2d8a268`** for `menu_item_variants`, `menu_items.stock_quantity`, `order_items.variant_id` and `restaurant_profile.logo`. One head, tested up, down and up, no drift between models and database. A test now fails if the migrations ever get two heads.
- **Screens:** sizes (one button per size when ordering; a *Sizes of ...* panel on the menu), stock (counts, low-stock and sold-out badges, restock or stop counting), logo upload (header and bill preview, with friendly refusals), and **Send on WhatsApp** on the bill.
- **Menu refresh:** the menu reloads after any order change that touches stock, so the numbers staff see are current.
- **Repository checks:** a test keeps `config.py`, `.env.example`, the README table, `package.json` and `requirements-frontend.txt` in step (two settings had been missing from `.env.example`).
- **`e2e/`:** the real-browser check (33 steps plus a layout check at phone, tablet and desktop widths) with its own isolated Docker stack `docker-compose.e2e.yml`.
- **README** rewritten where it was behind: Bookings and Retention sections (they had none), sizes and stock, sending bills, project structure, upgrade note for old local databases, configuration table, testing and out-of-scope lists.

**Real bugs the browser check found** (none were visible to unit tests, which do not load CSS or a real database)
1. A menu row's name overlapped its price when the row wrapped.
2. A CSS rule meant to hide the mobile menu button on desktop also hid every quantity +/- button, so on a desktop screen staff could not change or remove an order line (present since Stage 1).
3. Stock numbers on the order screen did not refresh after items were added, so a sold-out item still showed "2 left".
4. The daily report miscounted bills made in the 5½ hours after midnight in Delhi when the database ignored time zones. Day bounds are now converted to UTC explicitly.

**Decisions** (change if wrong)
- Stock is taken when an item is added to an order (not at billing) and given back if the line is reduced, removed or the order cancelled. This is what stops two waiters selling the last portion; it was verified with real concurrent requests on PostgreSQL (12 racers for 5 portions: exactly 5 winners).
- Stock belongs to the item and is shared by its sizes. Tax comes from the item.
- The logo is a PNG, JPEG or WebP under 100 KB stored in the database (SVG is refused because it can carry scripts, and the file's first bytes must match its type). The thermal bill text has no logo; it appears in the app header and on the bill preview.
- A bill sent on WhatsApp is a service message, so the marketing opt-out does not stop it.
- A guest over the bot's hourly limit gets a notice, the model is not called, and the message is not stored.

**Planned but deliberately not built**
- Card and UPI payment gateway, and direct thermal-printer (ESC/POS) control: they need a provider account or hardware, and receipts print through the browser.
- "Delivered" tracking for messages: depends on the WhatsApp provider.
- A visual drag-and-drop floor plan: the table grid already shows free and occupied tables.
- The VIP segment: removed on purpose by the other developer.

**Still open:** choosing and connecting a real WhatsApp provider, and running the bot against the real OpenAI API (no key has been configured here; everything around the model is tested with a scripted model).


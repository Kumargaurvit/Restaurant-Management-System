# End-to-end browser check

Unit tests cannot see layout or real database behaviour. This check drives the app in a real
browser against a real PostgreSQL database, the way a person would. It found three bugs that all
the unit tests missed (an overlapping menu row, buttons hidden by a CSS rule, and stale stock
numbers), so run it before a release.

## What it covers (33 steps)

Registering a restaurant, receipt details and logo (including refusing a non-image), staff, menu,
a counted item with sizes, a table, taking a dine-in order, the kitchen ticket, the GST bill,
payment, the receipt (with logo), sending the bill on WhatsApp, customers, insights, daily sales,
a booking made and confirmed, every Retention tab, an offer, the WhatsApp bot test chat, the
conversation queue, the webhook (wrong secret refused, `STOP` opt-out, a normal reply), selling an
item down to "Sold out" and getting the stock back by cancelling, and a waiter's limited access.

`mobile.cjs` also checks the layout at phone, tablet and desktop widths.

## Run it

You need Docker, Node.js 22+, and Chrome or Edge installed (it uses the one you have; no browser
download). From the repository root:

```bash
docker compose -p rmse2e -f docker-compose.yml -f docker-compose.e2e.yml up -d --build
cd e2e
npm install
npm test            # the 33-step click-through
npm run layout      # phone / tablet / desktop layout
cd ..
docker compose -p rmse2e -f docker-compose.yml -f docker-compose.e2e.yml down -v
```

`docker-compose.e2e.yml` gives the check its own database and ports (web 5174, API 8013), so it
never touches your normal data. Because the check registers a restaurant, it needs a fresh
database every run: always finish with `down -v`.

Failed steps save a screenshot to `e2e/output/`.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `E2E_WEB` | `http://localhost:5174` | Where the app is served |
| `E2E_API` | `http://localhost:8013` | Where the API is served |
| `E2E_WEBHOOK_SECRET` | `check-secret` | Must match `WHATSAPP_WEBHOOK_SECRET` in the compose file |
| `E2E_OWNER_CONTACT` | `98100 11111` | Must match `OWNER_CONTACT` in the compose file |
| `E2E_BROWSER` | auto | Path to Chrome or Edge if it is not found automatically |

The bot steps assume **no** OpenAI key (the compose file blanks it), so the bot gives its polite
fallback. The real model is covered by the backend tests with a scripted model.

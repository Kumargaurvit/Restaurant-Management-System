// Single source of truth for the app's modules. Used by the sidebar, dashboard and module pages.
// `live` modules have a real screen; the others show a placeholder until their stage is built.
export const MODULES = [
  {
    path: "billing",
    name: "Billing",
    stage: 1,
    live: true,
    summary: "Tables, orders, kitchen tickets, GST bills, payments, receipts and reports.",
  },
  {
    path: "chatbot",
    name: "WhatsApp Bot",
    stage: 2,
    live: false,
    summary: "Guests ask about offers, bills and table availability. Replies in their language.",
  },
  {
    path: "bookings",
    name: "Bookings",
    stage: 3,
    live: true,
    summary: "Dine-out table bookings, slots and reminders.",
  },
  {
    path: "retention",
    name: "Retention",
    stage: 4,
    live: true,
    summary: "RFM segments, campaigns and the approval queue.",
  },
];

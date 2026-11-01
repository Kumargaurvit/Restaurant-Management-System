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
    live: true,
    summary: "Offers, guest conversations and a test chat. The bot answers about offers, bills and free tables.",
  },
  {
    path: "bookings",
    name: "Bookings",
    stage: 3,
    live: false,
    summary: "Dine-out table bookings, slots and reminders.",
  },
  {
    path: "retention",
    name: "Retention",
    stage: 4,
    live: false,
    summary: "RFM segments, campaigns and the approval queue.",
  },
];

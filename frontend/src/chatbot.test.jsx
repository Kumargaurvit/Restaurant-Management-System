import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { billingApi } from "./test/fakeBilling.js";
import { CASHIER, OWNER, WAITER, baseRoutes, fail, mockApi, renderApp } from "./test/helpers.jsx";

const MANAGER = { id: 4, name: "Mira", email: "mira@test.com", role: "manager" };

const HAPPY = {
  id: 1, title: "Happy hour", description: "On all mains", discount_percent: "15.00",
  valid_from: null, valid_until: "2026-10-22T14:00:00Z", is_active: true, status: "active",
};
const EVENING = {
  id: 2, title: "Evening deal", description: "", discount_percent: "10.00",
  valid_from: "2026-10-22T14:00:00Z", valid_until: null, is_active: true, status: "upcoming",
};
const PAUSED = {
  id: 3, title: "Weekend", description: "Sat and Sun", discount_percent: null,
  valid_from: null, valid_until: null, is_active: false, status: "paused",
};

function openBot(user, routes = {}, tab) {
  const api = mockApi({ ...baseRoutes(user), ...routes });
  renderApp("/chatbot", { user });
  return { api, openTab: async () => tab && userEvent.click(await screen.findByRole("tab", { name: tab })) };
}

describe("Access", () => {
  it("is limited to owners and managers", async () => {
    openBot(WAITER);

    expect(await screen.findByText(/Only owners and managers can manage the WhatsApp bot/)).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Offers" })).not.toBeInTheDocument();
  });

  it("is available to a manager", async () => {
    openBot(MANAGER, { "GET /api/offers": [] });

    expect(await screen.findByRole("tab", { name: "Conversations" })).toBeInTheDocument();
  });
});

describe("Offers", () => {
  it("lists offers with their status and time window", async () => {
    openBot(OWNER, { "GET /api/offers": [HAPPY, EVENING, PAUSED] });

    const list = await screen.findByRole("list", { name: "Offers" });
    expect(within(list).getByText("Happy hour")).toBeInTheDocument();
    expect(within(list).getByText(/15% off/)).toBeInTheDocument();
    expect(within(list).getByText("active")).toBeInTheDocument();
    expect(within(list).getByText("upcoming")).toBeInTheDocument();
    expect(within(list).getByText("paused")).toBeInTheDocument();
    expect(within(list).getByText(/Until /)).toBeInTheDocument();
  });

  it("shows an empty state", async () => {
    openBot(OWNER, { "GET /api/offers": [] });

    expect(await screen.findByText("No offers yet.")).toBeInTheDocument();
  });

  it("creates an offer with a percentage and a time window", async () => {
    const { api } = openBot(OWNER, {
      "GET /api/offers": [],
      "POST /api/offers": { ...HAPPY, id: 9 },
    });
    const form = await screen.findByRole("form", { name: "Offer form" });

    await userEvent.type(within(form).getByLabelText("Title"), "Lunch deal");
    await userEvent.type(within(form).getByLabelText("Details (shown to guests)"), "Weekdays");
    await userEvent.type(within(form).getByLabelText("Discount (%)"), "12.5");
    await userEvent.type(within(form).getByLabelText("Starts (optional)"), "2026-10-23T12:00");
    await userEvent.type(within(form).getByLabelText("Ends (optional)"), "2026-10-23T15:00");
    await userEvent.click(within(form).getByRole("button", { name: "Add offer" }));

    await waitFor(() => expect(api.called("POST", "/api/offers")).toHaveLength(1));
    expect(api.called("POST", "/api/offers")[0].body).toEqual({
      title: "Lunch deal",
      description: "Weekdays",
      discount_percent: "12.5",
      valid_from: new Date("2026-10-23T12:00").toISOString(),
      valid_until: new Date("2026-10-23T15:00").toISOString(),
      is_active: true,
    });
  });

  it("sends no percentage and no times when those are left empty", async () => {
    const { api } = openBot(OWNER, { "GET /api/offers": [], "POST /api/offers": PAUSED });
    const form = await screen.findByRole("form", { name: "Offer form" });

    await userEvent.type(within(form).getByLabelText("Title"), "Free dessert");
    await userEvent.click(within(form).getByRole("button", { name: "Add offer" }));

    await waitFor(() => expect(api.called("POST", "/api/offers")).toHaveLength(1));
    expect(api.called("POST", "/api/offers")[0].body).toMatchObject({
      discount_percent: null,
      valid_from: null,
      valid_until: null,
    });
  });

  it("shows the server's message when an offer is rejected", async () => {
    openBot(OWNER, {
      "GET /api/offers": [],
      "POST /api/offers": fail(422, "Value error, The end time must be after the start time"),
    });
    const form = await screen.findByRole("form", { name: "Offer form" });

    await userEvent.type(within(form).getByLabelText("Title"), "Bad");
    await userEvent.click(within(form).getByRole("button", { name: "Add offer" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("The end time must be after the start time");
  });

  it("loads an offer into the form for editing and saves it with PUT", async () => {
    const { api } = openBot(OWNER, {
      "GET /api/offers": [HAPPY],
      "PUT /api/offers/1": HAPPY,
    });

    await userEvent.click(await screen.findByRole("button", { name: "Edit Happy hour" }));
    const form = screen.getByRole("form", { name: "Offer form" });
    expect(within(form).getByLabelText("Title")).toHaveValue("Happy hour");
    expect(within(form).getByLabelText("Discount (%)")).toHaveValue("15");
    const title = within(form).getByLabelText("Title");
    await userEvent.clear(title);
    await userEvent.type(title, "Late lunch");
    await userEvent.click(within(form).getByRole("button", { name: "Save offer" }));

    await waitFor(() => expect(api.called("PUT", "/api/offers/1")).toHaveLength(1));
    expect(api.called("PUT", "/api/offers/1")[0].body).toMatchObject({
      title: "Late lunch",
      discount_percent: "15",
      is_active: true,
    });
  });

  it("can cancel editing", async () => {
    openBot(OWNER, { "GET /api/offers": [HAPPY] });

    await userEvent.click(await screen.findByRole("button", { name: "Edit Happy hour" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.getByRole("heading", { name: "New offer" })).toBeInTheDocument();
    expect(screen.getByLabelText("Title")).toHaveValue("");
  });

  it("pauses and resumes an offer without changing anything else", async () => {
    const { api } = openBot(OWNER, {
      "GET /api/offers": [HAPPY, PAUSED],
      "PUT /api/offers/1": HAPPY,
      "PUT /api/offers/3": PAUSED,
    });

    await userEvent.click(await screen.findByRole("button", { name: "Pause Happy hour" }));
    await userEvent.click(screen.getByRole("button", { name: "Resume Weekend" }));

    await waitFor(() => expect(api.called("PUT", "/api/offers/1")).toHaveLength(1));
    expect(api.called("PUT", "/api/offers/1")[0].body).toMatchObject({
      title: "Happy hour",
      discount_percent: "15.00",
      is_active: false,
    });
    await waitFor(() => expect(api.called("PUT", "/api/offers/3")[0].body.is_active).toBe(true));
  });

  it("needs a second click to delete an offer", async () => {
    const { api } = openBot(OWNER, { "GET /api/offers": [HAPPY], "DELETE /api/offers/1": {} });

    await userEvent.click(await screen.findByRole("button", { name: "Delete Happy hour" }));
    expect(api.called("DELETE", "/api/offers/1")).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Keep" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete Happy hour" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm delete Happy hour" }));

    await waitFor(() => expect(api.called("DELETE", "/api/offers/1")).toHaveLength(1));
  });
});

describe("Conversations", () => {
  const WAITING = {
    id: 1, phone: "9810000002", customer_name: null, needs_human: true,
    handoff_reason: "Wants to book a table for Saturday", last_message_at: "2026-10-22T10:00:00Z",
    message_count: 2, last_message: "A team member will reply shortly.",
  };
  const FINE = {
    id: 2, phone: "9810000001", customer_name: "Asha", needs_human: false, handoff_reason: null,
    last_message_at: "2026-10-22T09:00:00Z", message_count: 4, last_message: "15% off for 2 hours",
  };
  const THREAD = (conversation, extra = {}) => ({
    ...conversation,
    messages: [
      { id: 1, role: "user", content: "any discount?", created_at: "2026-10-22T09:00:00Z" },
      { id: 2, role: "assistant", content: "15% off for 2 hours", created_at: "2026-10-22T09:00:05Z" },
    ],
    ...extra,
  });

  async function openConversations(routes = {}) {
    const bot = openBot(OWNER, { "GET /api/offers": [], ...routes }, "Conversations");
    await bot.openTab();
    return bot.api;
  }

  it("lists conversations and highlights the ones that need a person", async () => {
    await openConversations({ "GET /api/chat/conversations": [WAITING, FINE] });

    const list = await screen.findByRole("list", { name: "Conversations" });
    expect(within(list).getByText("Needs a person")).toBeInTheDocument();
    expect(within(list).getByText("Asha")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("1 guest needs a reply from a person.");
  });

  it("pluralises the waiting count", async () => {
    await openConversations({ "GET /api/chat/conversations": [WAITING, { ...WAITING, id: 5, phone: "9810000005" }] });

    expect(await screen.findByRole("status")).toHaveTextContent("2 guests need a reply from a person.");
  });

  it("shows an empty state", async () => {
    await openConversations({ "GET /api/chat/conversations": [] });

    expect(await screen.findByText(/No conversations yet/)).toBeInTheDocument();
  });

  it("opens a conversation to show the chat and why a person is needed", async () => {
    await openConversations({
      "GET /api/chat/conversations": [WAITING],
      "GET /api/chat/conversations/1": THREAD(WAITING),
    });

    await userEvent.click(await screen.findByRole("button", { name: /9810000002/ }));

    const panel = await screen.findByLabelText("Conversation");
    expect(within(panel).getByText(/Wants to book a table for Saturday/)).toBeInTheDocument();
    const thread = within(panel).getByRole("list", { name: "Chat messages" });
    expect(within(thread).getByText("any discount?")).toBeInTheDocument();
    expect(within(thread).getByText("15% off for 2 hours")).toBeInTheDocument();
    expect(within(thread).getByText("Guest")).toBeInTheDocument();
    expect(within(thread).getByText("Bot")).toBeInTheDocument();
  });

  it("marks a conversation as handled", async () => {
    let handled = false;
    const api = await openConversations({
      "GET /api/chat/conversations": () => [handled ? { ...WAITING, needs_human: false } : WAITING],
      "GET /api/chat/conversations/1": () => THREAD(WAITING, handled ? { needs_human: false } : {}),
      "POST /api/chat/conversations/1/resolve": () => {
        handled = true;
        return { ...WAITING, needs_human: false };
      },
    });

    await userEvent.click(await screen.findByRole("button", { name: /9810000002/ }));
    await userEvent.click(await screen.findByRole("button", { name: "Mark as handled" }));

    await waitFor(() => expect(api.called("POST", "/api/chat/conversations/1/resolve")).toHaveLength(1));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Mark as handled" })).not.toBeInTheDocument());
  });

  it("does not offer to mark a normal conversation as handled", async () => {
    await openConversations({
      "GET /api/chat/conversations": [FINE],
      "GET /api/chat/conversations/2": THREAD(FINE),
    });

    await userEvent.click(await screen.findByRole("button", { name: /Asha/ }));
    await screen.findByLabelText("Conversation");

    expect(screen.queryByRole("button", { name: "Mark as handled" })).not.toBeInTheDocument();
  });

  it("shows the server error if conversations cannot be loaded", async () => {
    await openConversations({ "GET /api/chat/conversations": fail(500, "Chat is down") });

    expect(await screen.findByRole("alert")).toHaveTextContent("Chat is down");
  });
});

describe("Test chat", () => {
  async function openTester(routes = {}) {
    const bot = openBot(OWNER, { "GET /api/offers": [], ...routes }, "Test chat");
    await bot.openTab();
    return bot.api;
  }

  it("sends a message as the guest and shows the bot's reply", async () => {
    const api = await openTester({
      "POST /api/chat/simulate": { reply: "Yes, we have space for 2!", needs_human: false },
    });
    const section = await screen.findByLabelText("Test chat");

    await userEvent.type(within(section).getByLabelText("Message"), "Is there space for 2?");
    await userEvent.click(within(section).getByRole("button", { name: "Send" }));

    const thread = await within(section).findByRole("list", { name: "Test conversation" });
    expect(within(thread).getByText("Is there space for 2?")).toBeInTheDocument();
    expect(await within(thread).findByText("Yes, we have space for 2!")).toBeInTheDocument();
    expect(api.called("POST", "/api/chat/simulate")[0].body).toEqual({
      phone: "9000000000",
      text: "Is there space for 2?",
    });
    expect(within(section).getByLabelText("Message")).toHaveValue("");
  });

  it("uses the guest number you type", async () => {
    const api = await openTester({ "POST /api/chat/simulate": { reply: "ok", needs_human: false } });
    const section = await screen.findByLabelText("Test chat");

    const phone = within(section).getByLabelText("Guest mobile number");
    await userEvent.clear(phone);
    await userEvent.type(phone, "9810000001");
    await userEvent.type(within(section).getByLabelText("Message"), "send my bill");
    await userEvent.click(within(section).getByRole("button", { name: "Send" }));

    await waitFor(() => expect(api.called("POST", "/api/chat/simulate")).toHaveLength(1));
    expect(api.called("POST", "/api/chat/simulate")[0].body.phone).toBe("9810000001");
  });

  it("cannot send an empty message", async () => {
    await openTester();

    expect(await screen.findByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("flags when the bot asks for a person", async () => {
    await openTester({
      "POST /api/chat/simulate": { reply: "A team member will help you.", needs_human: true },
    });
    const section = await screen.findByLabelText("Test chat");

    await userEvent.type(within(section).getByLabelText("Message"), "I want to book a table");
    await userEvent.click(within(section).getByRole("button", { name: "Send" }));

    expect(await within(section).findByText(/asked for a person to take over/)).toBeInTheDocument();
  });

  it("shows the server's message when sending fails, e.g. an invalid number", async () => {
    await openTester({
      "POST /api/chat/simulate": fail(422, "Enter a valid 10-digit mobile number"),
    });
    const section = await screen.findByLabelText("Test chat");

    await userEvent.type(within(section).getByLabelText("Message"), "hi");
    await userEvent.click(within(section).getByRole("button", { name: "Send" }));

    expect(await within(section).findByRole("alert")).toHaveTextContent("valid 10-digit mobile number");
  });
});

describe("Applying a running offer at billing", () => {
  const ACTIVE = [
    { ...HAPPY, status: "active" },
    { id: 7, title: "Free dessert", description: "", discount_percent: null, valid_from: null, valid_until: null, is_active: true, status: "active" },
  ];

  async function openOrder(user, offers) {
    const fake = billingApi(user);
    fake.routes["GET /api/offers/active"] = offers;
    mockApi(fake.routes);
    renderApp("/billing", { user });
    await userEvent.click(await screen.findByRole("button", { name: "T1 free" }));
    await userEvent.click(await screen.findByRole("button", { name: "Add Paneer Tikka" }));
    await screen.findByLabelText("Paneer Tikka quantity");
  }

  it("fills the discount with the offer's percentage of the subtotal", async () => {
    await openOrder(CASHIER, ACTIVE);

    await userEvent.click(await screen.findByRole("button", { name: "Apply Happy hour (15%)" }));

    expect(screen.getByLabelText("Discount (₹)")).toHaveValue("30.00"); // 15% of 200
  });

  it("only offers percentage-based offers", async () => {
    await openOrder(CASHIER, ACTIVE);

    await screen.findByRole("button", { name: "Apply Happy hour (15%)" });
    expect(screen.queryByRole("button", { name: /Free dessert/ })).not.toBeInTheDocument();
  });

  it("is not shown to a waiter, who cannot bill", async () => {
    await openOrder(WAITER, ACTIVE);

    expect(screen.queryByRole("button", { name: /Apply Happy hour/ })).not.toBeInTheDocument();
  });

  it("shows nothing when no offers are running", async () => {
    await openOrder(CASHIER, []);

    expect(screen.queryByLabelText("Running offers")).not.toBeInTheDocument();
  });
});

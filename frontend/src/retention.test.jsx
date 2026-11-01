import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { CASHIER, OWNER, baseRoutes, mockApi, renderApp } from "./test/helpers.jsx";

const member = {
  customer_id: 1,
  name: "Asha",
  phone: "9000000001",
  segment: "at_risk",
  visits: 3,
  total_spent: "1200.00",
  days_since_visit: 60,
  recency_score: 3,
  frequency_score: 3,
  monetary_score: 2,
  marketing_opt_out: false,
};

const rule = {
  id: 4,
  name: "Win back",
  segment: "at_risk",
  template: "Hi {name}, we miss you!",
  mode: "approval",
  cooldown_days: 30,
  is_active: true,
};

const pending = {
  id: 9,
  rule_id: 4,
  rule_name: "Win back",
  customer_id: 1,
  customer_name: "Asha",
  phone: "9000000001",
  body: "Hi Asha, we miss you!\nReply STOP to opt out.",
  status: "pending",
};

const routes = (user, overrides = {}) => ({
  ...baseRoutes(user),
  "GET /api/retention/segments": {
    summary: [
      { segment: "regular", customers: 0 },
      { segment: "new", customers: 0 },
      { segment: "at_risk", customers: 1 },
      { segment: "lost", customers: 0 },
    ],
    members: [member],
  },
  "GET /api/retention/settings": { at_risk_days: 45, lost_days: 90 },
  "GET /api/retention/rules": [rule],
  "GET /api/retention/messages": [pending],
  "GET /api/retention/report": [
    { rule_id: 4, rule_name: "Win back", pending: 1, sent: 5, failed: 0, rejected: 1, skipped: 0, replied: 2, visited_after: 1 },
  ],
  ...overrides,
});

describe("Retention page", () => {
  it("shows segment counts and each customer's scores", async () => {
    mockApi(routes(OWNER));
    renderApp("/retention", { user: OWNER });

    expect(await screen.findByRole("button", { name: "At risk (1)" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /VIP/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/VIP/)).not.toBeInTheDocument();
    const table = await screen.findByRole("table", { name: "Customer segments" });
    expect(within(table).getByText(/Asha/)).toBeInTheDocument();
    expect(within(table).getByText("60d ago")).toBeInTheDocument();
  });

  it("filters customers by segment", async () => {
    const api = mockApi(routes(OWNER));
    renderApp("/retention", { user: OWNER });

    await userEvent.click(await screen.findByRole("button", { name: "Lost (0)" }));

    await waitFor(() =>
      expect(api.calls.some((c) => c.path === "/api/retention/segments?segment=lost")).toBe(true),
    );
  });

  it("is limited to owners and managers", async () => {
    mockApi(routes(CASHIER));
    renderApp("/retention", { user: CASHIER });

    expect(await screen.findByText(/available to the owner and managers/)).toBeInTheDocument();
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
  });

  it("creates a campaign rule", async () => {
    const api = mockApi(routes(OWNER, { "POST /api/retention/rules": rule }));
    renderApp("/retention", { user: OWNER });

    await userEvent.click(await screen.findByRole("tab", { name: "Campaign rules" }));
    const form = await screen.findByRole("region", { name: "Rule form" });
    await userEvent.type(within(form).getByLabelText("Rule name"), "Comeback");
    await userEvent.selectOptions(within(form).getByLabelText("Sending"), "automatic");
    await userEvent.click(within(form).getByRole("button", { name: "Add rule" }));

    await waitFor(() => expect(api.called("POST", "/api/retention/rules")).toHaveLength(1));
    expect(api.called("POST", "/api/retention/rules")[0].body).toMatchObject({
      name: "Comeback",
      segment: "at_risk",
      mode: "automatic",
      cooldown_days: 30,
    });
  });

  it("runs the rules and reports what happened", async () => {
    mockApi(
      routes(OWNER, {
        "POST /api/retention/run": { rules_run: 1, queued: 2, sent: 0, skipped_cooldown: 1 },
      }),
    );
    renderApp("/retention", { user: OWNER });

    await userEvent.click(await screen.findByRole("tab", { name: "Campaign rules" }));
    await userEvent.click(await screen.findByRole("button", { name: "Run rules now" }));

    expect(await screen.findByRole("status")).toHaveTextContent("2 waiting for approval");
  });

  it("approves a queued message", async () => {
    const api = mockApi(
      routes(OWNER, { "POST /api/retention/messages/9/approve": { ...pending, status: "sent" } }),
    );
    renderApp("/retention", { user: OWNER });

    await userEvent.click(await screen.findByRole("tab", { name: "Approval queue" }));
    const queue = await screen.findByRole("list", { name: "Approval queue" });
    expect(within(queue).getByText(/Reply STOP to opt out/)).toBeInTheDocument();
    await userEvent.click(within(queue).getByRole("button", { name: "Approve message to Asha" }));

    await waitFor(() => expect(api.called("POST", "/api/retention/messages/9/approve")).toHaveLength(1));
  });

  it("rejects a queued message", async () => {
    const api = mockApi(
      routes(OWNER, { "POST /api/retention/messages/9/reject": { ...pending, status: "rejected" } }),
    );
    renderApp("/retention", { user: OWNER });

    await userEvent.click(await screen.findByRole("tab", { name: "Approval queue" }));
    await userEvent.click(await screen.findByRole("button", { name: "Reject message to Asha" }));

    await waitFor(() => expect(api.called("POST", "/api/retention/messages/9/reject")).toHaveLength(1));
  });

  it("shows campaign results", async () => {
    mockApi(routes(OWNER));
    renderApp("/retention", { user: OWNER });

    await userEvent.click(await screen.findByRole("tab", { name: "Results" }));
    const table = await screen.findByRole("table", { name: "Campaign results" });
    expect(within(table).getByText("Win back")).toBeInTheDocument();
    expect(within(table).getByText("5")).toBeInTheDocument();
  });
});

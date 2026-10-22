import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { billingApi } from "./test/fakeBilling.js";
import { OWNER, WAITER, fail, mockApi, renderApp } from "./test/helpers.jsx";

const phoneOf = (path) => new URL(`http://x${path}`).searchParams.get("phone");

const ASHA = {
  id: 77, phone: "9810000001", name: "Asha", visits: 4, total_spent: "1800.00",
  first_visit: "2026-09-01T10:00:00Z", last_visit: "2026-10-20T19:30:00Z", is_returning: true,
};
const BALA = {
  id: 78, phone: "9810000002", name: null, visits: 1, total_spent: "210.00",
  first_visit: "2026-10-01T10:00:00Z", last_visit: "2026-10-01T10:00:00Z", is_returning: false,
};

async function startDineIn(user, extraRoutes = {}) {
  const fake = billingApi(user);
  Object.assign(fake.routes, extraRoutes);
  const api = mockApi(fake.routes);
  renderApp("/billing", { user });
  await userEvent.click(await screen.findByRole("button", { name: "T1 free" }));
  await screen.findByRole("heading", { name: "Table order #1" });
  return { ...fake, api };
}

describe("Customer on an order", () => {
  it("recognises a returning guest while the number is typed and fills the name", async () => {
    await startDineIn(OWNER, {
      "GET /api/customers/lookup": ({ path }) =>
        phoneOf(path).replace(/\D/g, "").endsWith("9810000001")
          ? { id: 77, phone: "9810000001", name: "Asha", visits: 4, is_returning: true }
          : fail(404, "New customer"),
    });

    await userEvent.type(screen.getByLabelText("Guest mobile number"), "98100 00001");

    expect(await screen.findByRole("status")).toHaveTextContent("Returning customer: Asha, 4 visits");
    expect(screen.getByLabelText("Name (optional)")).toHaveValue("Asha");
  });

  it("says nothing for a number that is not known yet", async () => {
    await startDineIn(OWNER, { "GET /api/customers/lookup": fail(404, "New customer") });

    await userEvent.type(screen.getByLabelText("Guest mobile number"), "9810000009");

    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("saves the customer on the order and then shows who it is", async () => {
    const { api } = await startDineIn(OWNER, {
      "GET /api/customers/lookup": fail(404, "New customer"),
    });

    await userEvent.type(screen.getByLabelText("Guest mobile number"), "9810000009");
    await userEvent.type(screen.getByLabelText("Name (optional)"), "Neha");
    await userEvent.click(screen.getByRole("button", { name: "Save customer" }));

    const box = await screen.findByLabelText("Customer");
    expect(within(box).getByText("Neha")).toBeInTheDocument();
    expect(within(box).getByText(/9810000009/)).toBeInTheDocument();
    expect(api.called("PUT", "/api/billing/orders/1/customer")[0].body).toEqual({
      phone: "9810000009",
      name: "Neha",
    });
  });

  it("shows a Returning badge with the visit count for a returning guest", async () => {
    await startDineIn(OWNER, {
      "GET /api/customers/lookup": ({ path }) =>
        phoneOf(path).includes("9810000001")
          ? { id: 77, phone: "9810000001", name: "Asha", visits: 4, is_returning: true }
          : fail(404, "New customer"),
    });

    await userEvent.type(screen.getByLabelText("Guest mobile number"), "9810000001");
    await userEvent.click(screen.getByRole("button", { name: "Save customer" }));

    const box = await screen.findByLabelText("Customer");
    expect(await within(box).findByText("Returning · 4 visits")).toBeInTheDocument();
  });

  it("shows the server's message for an invalid number", async () => {
    await startDineIn(OWNER, { "GET /api/customers/lookup": fail(404, "New customer"),
      "PUT /api/billing/orders/1/customer": fail(422, "Enter a valid 10-digit mobile number") });

    await userEvent.type(screen.getByLabelText("Guest mobile number"), "123");
    await userEvent.click(screen.getByRole("button", { name: "Save customer" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Enter a valid 10-digit mobile number");
  });

  it("does not allow saving without a number", async () => {
    await startDineIn(OWNER);

    expect(screen.getByRole("button", { name: "Save customer" })).toBeDisabled();
  });

  it("lets a waiter attach a customer too", async () => {
    await startDineIn(WAITER);

    expect(screen.getByLabelText("Guest mobile number")).toBeInTheDocument();
  });

  it("lets the customer be changed while the order is open", async () => {
    await startDineIn(OWNER, { "GET /api/customers/lookup": fail(404, "New customer") });
    await userEvent.type(screen.getByLabelText("Guest mobile number"), "9810000009");
    await userEvent.click(screen.getByRole("button", { name: "Save customer" }));
    await screen.findByLabelText("Customer");

    await userEvent.click(screen.getByRole("button", { name: "Change" }));

    expect(screen.getByLabelText("Guest mobile number")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByLabelText("Customer")).toBeInTheDocument();
  });
});

describe("Customers tab", () => {
  async function openCustomers(routes = {}, user = OWNER) {
    const fake = billingApi(user);
    Object.assign(fake.routes, {
      "GET /api/customers": [ASHA, BALA],
      ...routes,
    });
    const api = mockApi(fake.routes);
    renderApp("/billing", { user });
    await userEvent.click(await screen.findByRole("tab", { name: "Customers" }));
    return api;
  }

  it("is hidden from a waiter", async () => {
    const fake = billingApi(WAITER);
    mockApi(fake.routes);
    renderApp("/billing", { user: WAITER });
    await screen.findByRole("heading", { name: "Billing" });

    expect(screen.queryByRole("tab", { name: "Customers" })).not.toBeInTheDocument();
  });

  it("lists customers with visits and spend", async () => {
    await openCustomers();

    const list = await screen.findByRole("list", { name: "Customers" });
    expect(within(list).getByText("Asha")).toBeInTheDocument();
    expect(within(list).getByText(/4 visits/)).toBeInTheDocument();
    expect(within(list).getByText(/₹1800.00/)).toBeInTheDocument();
    expect(within(list).getByText("Guest")).toBeInTheDocument();
    expect(within(list).getByText(/1 visit ·/)).toBeInTheDocument();
  });

  it("searches by name or number", async () => {
    const api = await openCustomers();
    await screen.findByRole("list", { name: "Customers" });

    await userEvent.type(screen.getByLabelText("Search by name or number"), "asha");

    await waitFor(() =>
      expect(api.calls.some((c) => c.path === "/api/customers?search=asha")).toBe(true),
    );
  });

  it("shows an empty message when there are no customers", async () => {
    await openCustomers({ "GET /api/customers": [] });

    expect(await screen.findByText(/No customers yet/)).toBeInTheDocument();
  });

  it("opens a customer to show favourite dishes and order history", async () => {
    await openCustomers({
      "GET /api/customers/77": {
        ...ASHA,
        favourite_dishes: [{ menu_item_id: 10, name: "Paneer Tikka", quantity: 9, orders: 4, revenue: "1800.00" }],
        orders: [
          {
            order_id: 5, invoice_number: "INV-2026-000005", billed_at: "2026-10-20T19:30:00Z",
            order_type: "dine_in", bill_status: "paid", total: "538.00",
            items: [{ name: "Paneer Tikka", quantity: 2 }, { name: "Cola", quantity: 2 }],
          },
        ],
      },
    });

    await userEvent.click(await screen.findByRole("button", { name: /Asha/ }));

    const details = await screen.findByLabelText("Customer details");
    expect(within(details).getByText("9810000001")).toBeInTheDocument();
    const favourites = within(details).getByRole("list", { name: "Favourite dishes" });
    expect(within(favourites).getByText("Paneer Tikka")).toBeInTheDocument();
    expect(within(favourites).getByText("× 9")).toBeInTheDocument();
    const history = within(details).getByRole("list", { name: "Order history" });
    expect(within(history).getByText("INV-2026-000005")).toBeInTheDocument();
    expect(within(history).getByText("2 × Paneer Tikka, 2 × Cola")).toBeInTheDocument();
    expect(within(history).getByText("₹538.00")).toBeInTheDocument();
  });

  it("shows the server error if the list cannot be loaded", async () => {
    await openCustomers({ "GET /api/customers": fail(500, "Something broke") });

    expect(await screen.findByRole("alert")).toHaveTextContent("Something broke");
  });
});

describe("Insights tab", () => {
  const DISHES = [
    { menu_item_id: 10, name: "Paneer Tikka", quantity: 42, orders: 30, revenue: "8400.00" },
    { menu_item_id: 11, name: "Cola", quantity: 17, orders: 12, revenue: "850.00" },
  ];

  async function openInsights(routes = {}) {
    const fake = billingApi(OWNER);
    Object.assign(fake.routes, {
      "GET /api/reports/top-dishes": DISHES,
      "GET /api/reports/top-customers": [ASHA, BALA],
      ...routes,
    });
    const api = mockApi(fake.routes);
    renderApp("/billing", { user: OWNER });
    await userEvent.click(await screen.findByRole("tab", { name: "Insights" }));
    return api;
  }

  it("ranks the most ordered dishes", async () => {
    await openInsights();

    const table = await screen.findByRole("table", { name: "Most ordered dishes" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(within(rows[0]).getByText("Paneer Tikka")).toBeInTheDocument();
    expect(within(rows[0]).getByText("42")).toBeInTheDocument();
    expect(within(rows[0]).getByText("₹8400.00")).toBeInTheDocument();
    expect(within(rows[1]).getByText("Cola")).toBeInTheDocument();
  });

  it("ranks the most frequent customers and flags returning ones", async () => {
    await openInsights();

    const table = await screen.findByRole("table", { name: "Most frequent customers" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(within(rows[0]).getByText("Asha")).toBeInTheDocument();
    expect(within(rows[0]).getByText("4")).toBeInTheDocument();
    expect(within(rows[0]).getByText("Returning")).toBeInTheDocument();
    expect(within(rows[1]).queryByText("Returning")).not.toBeInTheDocument();
  });

  it("defaults to the last 30 days and refetches when the period changes", async () => {
    const api = await openInsights();
    await screen.findByRole("table", { name: "Most ordered dishes" });
    expect(api.calls.some((c) => c.path === "/api/reports/top-dishes?days=30&limit=10")).toBe(true);

    await userEvent.selectOptions(screen.getByLabelText("Period"), "All time");

    await waitFor(() =>
      expect(api.calls.some((c) => c.path === "/api/reports/top-dishes?limit=10")).toBe(true),
    );
    expect(api.calls.some((c) => c.path === "/api/reports/top-customers?limit=10")).toBe(true);
  });

  it("explains how to start tracking when there is no data", async () => {
    await openInsights({
      "GET /api/reports/top-dishes": [],
      "GET /api/reports/top-customers": [],
    });

    expect(await screen.findByText("No billed orders in this period yet.")).toBeInTheDocument();
    expect(screen.getByText(/Add a guest's mobile number to an order/)).toBeInTheDocument();
  });

  it("shows the server error if the reports cannot be loaded", async () => {
    await openInsights({ "GET /api/reports/top-dishes": fail(500, "Report failed") });

    expect(await screen.findByRole("alert")).toHaveTextContent("Report failed");
  });
});

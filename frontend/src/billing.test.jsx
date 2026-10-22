import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { MENU, billingApi } from "./test/fakeBilling.js";
import { CASHIER, OWNER, WAITER, fail, mockApi, renderApp } from "./test/helpers.jsx";

async function openBilling(user, seed) {
  const fake = billingApi(user, seed);
  const api = mockApi(fake.routes);
  renderApp("/billing", { user });
  await screen.findByRole("heading", { name: "Billing" });
  return { ...fake, api };
}

const openTable = async (name) => userEvent.click(await screen.findByRole("button", { name: `${name} free` }));
const addItem = async (name) => userEvent.click(await screen.findByRole("button", { name: `Add ${name}` }));

describe("Tabs and permissions", () => {
  it("shows Orders, Menu & tables and Reports to the owner", async () => {
    await openBilling(OWNER);

    expect(screen.getByRole("tab", { name: "Orders" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Menu & tables" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Reports" })).toBeInTheDocument();
  });

  it("hides Menu and Reports from a waiter", async () => {
    await openBilling(WAITER);

    expect(screen.getByRole("tab", { name: "Orders" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Menu & tables" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Reports" })).not.toBeInTheDocument();
  });

  it("does not let a waiter generate a bill", async () => {
    await openBilling(WAITER);
    await openTable("T1");
    await addItem("Paneer Tikka");

    expect(screen.getByRole("button", { name: "Send to kitchen" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Generate bill" })).not.toBeInTheDocument();
  });

  it("lets a cashier bill but not manage the menu", async () => {
    await openBilling(CASHIER);
    await openTable("T1");
    await addItem("Paneer Tikka");

    expect(screen.getByRole("button", { name: "Generate bill" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Menu & tables" })).not.toBeInTheDocument();
  });
});

describe("Taking an order", () => {
  it("lists tables as free and marks tables with an open order as occupied", async () => {
    const existing = {
      id: 1, order_type: "dine_in", status: "open", table_id: 2, items: [],
      customer_name: null, customer_phone: null, delivery_address: null,
    };
    await openBilling(OWNER, { orders: [existing] });

    expect(await screen.findByRole("button", { name: "T2 occupied" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "T1 free" })).toBeInTheDocument();
  });

  it("opens a dine-in order for the tapped table", async () => {
    const { api } = await openBilling(OWNER);

    await openTable("T1");

    expect(await screen.findByRole("heading", { name: "Table order #1" })).toBeInTheDocument();
    expect(api.called("POST", "/api/billing/orders")[0].body).toEqual({
      order_type: "dine_in",
      table_id: 1,
    });
  });

  it("starts a takeaway order without a table", async () => {
    const { api } = await openBilling(OWNER);

    await userEvent.click(await screen.findByRole("button", { name: "New takeaway" }));

    expect(await screen.findByRole("heading", { name: "Takeaway order #1" })).toBeInTheDocument();
    expect(api.called("POST", "/api/billing/orders")[0].body).toEqual({ order_type: "takeaway" });
  });

  it("starts a delivery order with the customer's details", async () => {
    const { api } = await openBilling(OWNER);

    await userEvent.click(await screen.findByRole("button", { name: "New delivery" }));
    await userEvent.type(screen.getByLabelText("Customer name"), "Neha");
    await userEvent.type(screen.getByLabelText("Phone"), "9999999999");
    await userEvent.type(screen.getByLabelText("Delivery address"), "12 Lodhi Road, Delhi");
    await userEvent.click(screen.getByRole("button", { name: "Start order" }));

    expect(await screen.findByRole("heading", { name: "Delivery order #1" })).toBeInTheDocument();
    expect(api.called("POST", "/api/billing/orders")[0].body).toEqual({
      order_type: "delivery",
      customer_name: "Neha",
      customer_phone: "9999999999",
      delivery_address: "12 Lodhi Road, Delhi",
    });
  });

  it("adds an item and merges repeated taps into one line", async () => {
    await openBilling(OWNER);
    await openTable("T1");

    await addItem("Paneer Tikka");
    await addItem("Paneer Tikka");

    const lines = within(screen.getByRole("list", { name: "Order items" })).getAllByRole("listitem");
    expect(lines).toHaveLength(1);
    expect(screen.getByLabelText("Paneer Tikka quantity")).toHaveTextContent("2");
  });

  it("does not offer unavailable items", async () => {
    await openBilling(OWNER);
    await openTable("T1");

    await screen.findByRole("button", { name: "Add Paneer Tikka" });
    expect(screen.queryByRole("button", { name: "Add Sold Out Soup" })).not.toBeInTheDocument();
  });

  it("changes quantity with the stepper and removes a line at zero", async () => {
    await openBilling(OWNER);
    await openTable("T1");
    await addItem("Paneer Tikka");

    await userEvent.click(screen.getByRole("button", { name: "Increase Paneer Tikka" }));
    await waitFor(() =>
      expect(screen.getByLabelText("Paneer Tikka quantity")).toHaveTextContent("2"),
    );
    await userEvent.click(screen.getByRole("button", { name: "Decrease Paneer Tikka" }));
    await userEvent.click(screen.getByRole("button", { name: "Decrease Paneer Tikka" }));

    expect(await screen.findByText("Tap a menu item to add it.")).toBeInTheDocument();
  });

  it("shows the server's message when an item cannot be added", async () => {
    const fake = billingApi(OWNER);
    fake.routes["POST /api/billing/orders/1/items"] = fail(409, "Cola is not available");
    mockApi(fake.routes);
    renderApp("/billing", { user: OWNER });
    await openTable("T1");

    await addItem("Cola");

    expect(await screen.findByRole("alert")).toHaveTextContent("Cola is not available");
  });
});

describe("Kitchen ticket", () => {
  it("prints the kitchen ticket and marks lines as sent", async () => {
    await openBilling(OWNER);
    await openTable("T1");
    await addItem("Paneer Tikka");

    await userEvent.click(screen.getByRole("button", { name: "Send to kitchen" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/2 x Paneer Tikka/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(screen.getByText("sent")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send to kitchen" })).toBeDisabled();
  });
});

describe("Billing and payment", () => {
  async function toBill(user = OWNER, discount) {
    const ctx = await openBilling(user);
    await openTable("T1");
    await addItem("Paneer Tikka");
    if (discount) await userEvent.type(screen.getByLabelText("Discount (₹)"), discount);
    await userEvent.click(screen.getByRole("button", { name: "Generate bill" }));
    return ctx;
  }

  it("generates a bill with GST and total", async () => {
    await toBill();

    const bill = await screen.findByLabelText("Bill");
    expect(within(bill).getByText("INV-2026-000001", { exact: false })).toBeInTheDocument();
    expect(within(bill).getByText("CGST").nextSibling).toHaveTextContent("₹19.00");
    expect(within(bill).getByText("Total").nextSibling).toHaveTextContent("₹538.00");
  });

  it("sends the discount with the bill and shows it", async () => {
    const { api } = await toBill(OWNER, "38");

    const bill = await screen.findByLabelText("Bill");
    expect(api.called("POST", "/api/billing/orders/1/bill")[0].body).toEqual({ discount: "38" });
    expect(within(bill).getByText("Total").nextSibling).toHaveTextContent("₹500.00");
  });

  it("takes a payment and marks the bill paid", async () => {
    const { api } = await toBill();
    await screen.findByLabelText("Bill");

    expect(screen.getByLabelText("Amount (₹)")).toHaveValue("538.00");
    await userEvent.click(screen.getByRole("button", { name: "Take payment" }));

    expect(await screen.findByText("Paid", { selector: ".badge" })).toBeInTheDocument();
    expect(api.called("POST", "/api/billing/bills/10/payments")[0].body).toEqual({
      mode: "cash",
      amount: "538.00",
      reference: null,
    });
    expect(screen.queryByRole("button", { name: "Take payment" })).not.toBeInTheDocument();
  });

  it("records a UPI payment with its reference", async () => {
    const { api } = await toBill();
    await screen.findByLabelText("Bill");

    await userEvent.selectOptions(screen.getByLabelText("Mode"), "upi");
    await userEvent.type(screen.getByLabelText("Reference"), "UPI-123");
    await userEvent.click(screen.getByRole("button", { name: "Take payment" }));

    await waitFor(() => expect(api.called("POST", "/api/billing/bills/10/payments")).toHaveLength(1));
    expect(api.called("POST", "/api/billing/bills/10/payments")[0].body).toMatchObject({
      mode: "upi",
      reference: "UPI-123",
    });
  });

  it("shows the receipt text and offers to print it", async () => {
    await toBill();
    await screen.findByLabelText("Bill");

    await userEvent.click(screen.getByRole("button", { name: "Print receipt" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/RECEIPT TEXT for order 1/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Print" })).toBeInTheDocument();
  });

  it("lists unpaid bills and reopens one to collect payment", async () => {
    const order = {
      id: 1, order_type: "dine_in", status: "billed", table_id: 1, items: [],
      customer_name: null, customer_phone: null, delivery_address: null,
    };
    const bill = {
      id: 10, invoice_number: "INV-2026-000001", order_id: 1, subtotal: "500.00", discount: "0.00",
      cgst: "19.00", sgst: "19.00", round_off: "0.00", total: "538.00", status: "unpaid",
      payments: [], amount_paid: "0.00", amount_due: "538.00",
    };
    await openBilling(CASHIER, { orders: [order], bills: [bill] });

    await userEvent.click(await screen.findByRole("button", { name: /INV-2026-000001 · due ₹538.00/ }));

    const shown = await screen.findByLabelText("Bill");
    expect(within(shown).getByText("Due").nextSibling).toHaveTextContent("₹538.00");
    expect(screen.getByRole("button", { name: "Take payment" })).toBeInTheDocument();
  });
});

describe("Menu and tables", () => {
  it("adds a category", async () => {
    const fake = billingApi(OWNER);
    fake.routes["POST /api/billing/menu/categories"] = { id: 2, name: "Drinks", sort_order: 0 };
    const api = mockApi(fake.routes);
    renderApp("/billing", { user: OWNER });
    await userEvent.click(await screen.findByRole("tab", { name: "Menu & tables" }));

    await userEvent.type(screen.getByLabelText("New category"), "Drinks");
    await userEvent.click(screen.getByRole("button", { name: "Add category" }));

    await waitFor(() =>
      expect(api.called("POST", "/api/billing/menu/categories")[0].body).toEqual({ name: "Drinks" }),
    );
  });

  it("adds a menu item with a numeric category and the chosen GST rate", async () => {
    const fake = billingApi(OWNER);
    fake.routes["POST /api/billing/menu/items"] = { id: 20 };
    const api = mockApi(fake.routes);
    renderApp("/billing", { user: OWNER });
    await userEvent.click(await screen.findByRole("tab", { name: "Menu & tables" }));

    await userEvent.selectOptions(screen.getByLabelText("Category"), "1");
    await userEvent.type(screen.getByLabelText("Item name"), "Naan");
    await userEvent.type(screen.getByLabelText("Price (₹, excluding GST)"), "40");
    await userEvent.selectOptions(screen.getByLabelText("GST rate"), "12");
    await userEvent.click(screen.getByRole("button", { name: "Add item" }));

    await waitFor(() =>
      expect(api.called("POST", "/api/billing/menu/items")[0].body).toEqual({
        category_id: 1,
        name: "Naan",
        price: "40",
        gst_rate: "12",
      }),
    );
  });

  it("marks an item unavailable", async () => {
    const fake = billingApi(OWNER);
    fake.routes["PATCH /api/billing/menu/items/10"] = { ...MENU[0], is_available: false };
    const api = mockApi(fake.routes);
    renderApp("/billing", { user: OWNER });
    await userEvent.click(await screen.findByRole("tab", { name: "Menu & tables" }));

    const row = (await screen.findByText("Paneer Tikka")).closest("li");
    await userEvent.click(within(row).getByRole("button", { name: "Mark unavailable" }));

    await waitFor(() =>
      expect(api.called("PATCH", "/api/billing/menu/items/10")[0].body).toEqual({
        is_available: false,
      }),
    );
  });

  it("adds a table", async () => {
    const fake = billingApi(OWNER);
    fake.routes["POST /api/billing/tables"] = { id: 3, name: "T3", capacity: 6, is_active: true };
    const api = mockApi(fake.routes);
    renderApp("/billing", { user: OWNER });
    await userEvent.click(await screen.findByRole("tab", { name: "Menu & tables" }));

    await userEvent.type(screen.getByLabelText("Table name"), "T3");
    await userEvent.clear(screen.getByLabelText("Seats"));
    await userEvent.type(screen.getByLabelText("Seats"), "6");
    await userEvent.click(screen.getByRole("button", { name: "Add table" }));

    await waitFor(() =>
      expect(api.called("POST", "/api/billing/tables")[0].body).toEqual({ name: "T3", capacity: 6 }),
    );
  });

  it("shows a server error such as a duplicate category", async () => {
    const fake = billingApi(OWNER);
    fake.routes["POST /api/billing/menu/categories"] = fail(409, "Category already exists");
    mockApi(fake.routes);
    renderApp("/billing", { user: OWNER });
    await userEvent.click(await screen.findByRole("tab", { name: "Menu & tables" }));

    await userEvent.type(screen.getByLabelText("New category"), "Mains");
    await userEvent.click(screen.getByRole("button", { name: "Add category" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Category already exists");
  });
});

describe("Reports", () => {
  it("shows the daily sales totals", async () => {
    const fake = billingApi(OWNER);
    fake.routes["GET /api/billing/reports/daily"] = {
      day: "2026-10-22",
      bill_count: 7,
      total_sales: "4200.00",
      cash: "1500.00",
      upi: "2200.00",
      card: "500.00",
    };
    mockApi(fake.routes);
    renderApp("/billing", { user: OWNER });
    await userEvent.click(await screen.findByRole("tab", { name: "Reports" }));

    expect(await screen.findByText("₹4200.00")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("₹2200.00")).toBeInTheDocument();
  });
});

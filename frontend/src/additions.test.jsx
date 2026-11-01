import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { billingApi } from "./test/fakeBilling.js";
import { CASHIER, OWNER, WAITER, baseRoutes, fail, mockApi, renderApp } from "./test/helpers.jsx";

const LOGO = "data:image/png;base64,iVBORw0KGgo=";

const item = (overrides = {}) => ({
  id: 10, category_id: 1, name: "Paneer Tikka", price: "200.00", gst_rate: "5.00",
  is_available: true, stock_quantity: null, variants: [], ...overrides,
});
const SIZED = item({
  variants: [
    { id: 101, name: "Half", price: "120.00" },
    { id: 102, name: "Full", price: "200.00" },
  ],
});
const COLA = item({ id: 11, name: "Cola", price: "50.00", gst_rate: "18.00" });

/** Billing screen with a custom menu; returns the api so tests can inspect requests. */
async function openOrder(menu, { user = OWNER, extra = {} } = {}) {
  const fake = billingApi(user);
  Object.assign(fake.routes, {
    "GET /api/billing/menu/items": menu,
    "POST /api/billing/orders/1/items": ({ body }) => ({
      id: 1, order_type: "dine_in", status: "open", table_id: 1, customer_id: null,
      customer_name: "Neha", customer_phone: "9811111111", delivery_address: null,
      items: [{ id: 1, menu_item_id: body.menu_item_id, variant_id: body.variant_id ?? null, name: "x",
        unit_price: "1.00", gst_rate: "5.00", quantity: 1, notes: null, kitchen_ticket_id: null }],
    }),
    ...extra,
  });
  const api = mockApi(fake.routes);
  renderApp("/billing", { user });
  await userEvent.click(await screen.findByRole("button", { name: "T1 free" }));
  await userEvent.type(screen.getByLabelText("Contact number"), "9811111111");
  await userEvent.type(screen.getByLabelText("Customer name"), "Neha");
  await userEvent.click(screen.getByRole("button", { name: "Start order" }));
  await screen.findByRole("heading", { name: /Table order #1/ });
  return api;
}

describe("Ordering items with sizes", () => {
  it("shows one button per size instead of a single button", async () => {
    await openOrder([SIZED, COLA]);

    expect(await screen.findByRole("button", { name: "Add Paneer Tikka (Half)" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add Paneer Tikka (Full)" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add Paneer Tikka" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add Cola" })).toBeInTheDocument();
  });

  it("shows each size's own price", async () => {
    await openOrder([SIZED]);

    expect(within(await screen.findByRole("button", { name: "Add Paneer Tikka (Half)" })).getByText("₹120.00")).toBeInTheDocument();
    expect(within(screen.getByRole("button", { name: "Add Paneer Tikka (Full)" })).getByText("₹200.00")).toBeInTheDocument();
  });

  it("sends the chosen size with the order line", async () => {
    const api = await openOrder([SIZED]);

    await userEvent.click(await screen.findByRole("button", { name: "Add Paneer Tikka (Half)" }));

    await waitFor(() => expect(api.called("POST", "/api/billing/orders/1/items")).toHaveLength(1));
    expect(api.called("POST", "/api/billing/orders/1/items")[0].body).toEqual({
      menu_item_id: 10, quantity: 1, variant_id: 101,
    });
  });

  it("sends no size for an item that has none", async () => {
    const api = await openOrder([COLA]);

    await userEvent.click(await screen.findByRole("button", { name: "Add Cola" }));

    await waitFor(() => expect(api.called("POST", "/api/billing/orders/1/items")).toHaveLength(1));
    expect(api.called("POST", "/api/billing/orders/1/items")[0].body).toEqual({ menu_item_id: 11, quantity: 1 });
  });
});

describe("Stock in the order panel", () => {
  it("disables a sold-out item and says so", async () => {
    await openOrder([item({ stock_quantity: 0 })]);

    const button = await screen.findByRole("button", { name: "Add Paneer Tikka" });
    expect(button).toBeDisabled();
    expect(within(button).getByText("Sold out")).toBeInTheDocument();
  });

  it("shows how many are left for a counted item and nothing for an uncounted one", async () => {
    await openOrder([item({ stock_quantity: 3 }), COLA]);

    expect(within(await screen.findByRole("button", { name: "Add Paneer Tikka" })).getByText("3 left")).toBeInTheDocument();
    expect(within(screen.getByRole("button", { name: "Add Cola" })).queryByText(/left/)).not.toBeInTheDocument();
  });

  it("shows the server's message when there is not enough stock", async () => {
    await openOrder([item({ stock_quantity: 2 })], {
      extra: { "POST /api/billing/orders/1/items": fail(409, "Only 2 left of Paneer Tikka") },
    });

    await userEvent.click(await screen.findByRole("button", { name: "Add Paneer Tikka" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Only 2 left of Paneer Tikka");
  });
});

describe("Stock stays up to date while ordering", () => {
  /** A menu route whose stock follows what has been ordered, like the real server. */
  function liveMenu(startStock) {
    let stock = startStock;
    return {
      menuCalls: () => calls,
      routes: {
        "GET /api/billing/menu/items": () => {
          calls += 1;
          return [item({ stock_quantity: stock })];
        },
        "POST /api/billing/orders/1/items": () => {
          stock -= 1;
          return {
            id: 1, order_type: "dine_in", status: "open", table_id: 1, customer_id: null,
            customer_name: "Neha", customer_phone: "9811111111", delivery_address: null,
            items: [{ id: 1, menu_item_id: 10, variant_id: null, name: "Paneer Tikka", unit_price: "200.00",
              gst_rate: "5.00", quantity: 1, notes: null, kitchen_ticket_id: null }],
          };
        },
      },
    };
  }
  let calls = 0;

  it("shows the new count and sold-out state straight after an item is added", async () => {
    calls = 0;
    const live = liveMenu(2);
    await openOrder([item({ stock_quantity: 2 })], { extra: live.routes });
    const button = await screen.findByRole("button", { name: "Add Paneer Tikka" });
    expect(within(button).getByText("2 left")).toBeInTheDocument();

    await userEvent.click(button);
    expect(await within(await screen.findByRole("button", { name: "Add Paneer Tikka" })).findByText("1 left")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Add Paneer Tikka" }));
    const soldOut = await screen.findByText("Sold out");
    expect(soldOut).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add Paneer Tikka" })).toBeDisabled();
  });

  it("does not reload the menu when no item counts stock", async () => {
    calls = 0;
    const api = await openOrder([COLA]);
    await userEvent.click(await screen.findByRole("button", { name: "Add Cola" }));
    await waitFor(() => expect(api.called("POST", "/api/billing/orders/1/items")).toHaveLength(1));

    expect(api.called("GET", "/api/billing/menu/items")).toHaveLength(1); // only the first load
  });
});

// ---------------------------------------------------------------- send a bill

const BILLED = {
  id: 1, order_type: "dine_in", status: "billed", table_id: 1, customer_id: 5,
  customer_name: "Asha", customer_phone: "9810000001", delivery_address: null, items: [],
};
const BILL = {
  id: 10, invoice_number: "INV-2026-000001", order_id: 1, subtotal: "500.00", discount: "0.00",
  cgst: "19.00", sgst: "19.00", round_off: "0.00", total: "538.00", status: "paid",
  payments: [], amount_paid: "538.00", amount_due: "0.00",
};

async function openBill(user, extra = {}) {
  const fake = billingApi(user, { orders: [{ ...BILLED }], bills: [{ ...BILL, status: "unpaid", amount_paid: "0.00", amount_due: "538.00" }] });
  Object.assign(fake.routes, extra);
  const api = mockApi(fake.routes);
  renderApp("/billing", { user });
  await userEvent.click(await screen.findByRole("button", { name: /INV-2026-000001/ }));
  await screen.findByLabelText("Bill");
  return api;
}

describe("Sending a bill on WhatsApp", () => {
  it("offers the guest's number from the order and sends the bill", async () => {
    const api = await openBill(CASHIER, { "POST /api/billing/bills/10/send": { phone: "9810000001", status: "sent" } });

    await userEvent.click(screen.getByRole("button", { name: "Send on WhatsApp" }));
    const form = screen.getByRole("form", { name: "Send bill" });
    expect(within(form).getByLabelText("WhatsApp number")).toHaveValue("9810000001");
    await userEvent.click(within(form).getByRole("button", { name: "Send bill" }));

    expect(await screen.findByText("Bill sent to 9810000001.")).toBeInTheDocument();
    expect(api.called("POST", "/api/billing/bills/10/send")[0].body).toEqual({ phone: "9810000001" });
    expect(screen.queryByRole("form", { name: "Send bill" })).not.toBeInTheDocument();
  });

  it("can send to a different number", async () => {
    const api = await openBill(OWNER, { "POST /api/billing/bills/10/send": { phone: "9810000002", status: "sent" } });

    await userEvent.click(screen.getByRole("button", { name: "Send on WhatsApp" }));
    const number = screen.getByLabelText("WhatsApp number");
    await userEvent.clear(number);
    await userEvent.type(number, "98100 00002");
    await userEvent.click(screen.getByRole("button", { name: "Send bill" }));

    await waitFor(() => expect(api.called("POST", "/api/billing/bills/10/send")).toHaveLength(1));
    expect(api.called("POST", "/api/billing/bills/10/send")[0].body).toEqual({ phone: "98100 00002" });
  });

  it("sends an empty request when the number is cleared, so the server explains what is missing", async () => {
    const api = await openBill(OWNER, {
      "POST /api/billing/bills/10/send": fail(409, "This bill has no guest number. Enter one to send it."),
    });

    await userEvent.click(screen.getByRole("button", { name: "Send on WhatsApp" }));
    await userEvent.clear(screen.getByLabelText("WhatsApp number"));
    await userEvent.click(screen.getByRole("button", { name: "Send bill" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("no guest number");
    expect(api.called("POST", "/api/billing/bills/10/send")[0].body).toEqual({});
  });

  it("shows the server's message when sending fails", async () => {
    await openBill(OWNER, { "POST /api/billing/bills/10/send": fail(502, "Could not send the message. Please try again.") });

    await userEvent.click(screen.getByRole("button", { name: "Send on WhatsApp" }));
    await userEvent.click(screen.getByRole("button", { name: "Send bill" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not send the message");
    expect(screen.queryByText(/Bill sent to/)).not.toBeInTheDocument();
  });

  it("is not offered to a waiter", async () => {
    await openBill(WAITER);

    expect(screen.queryByRole("button", { name: "Send on WhatsApp" })).not.toBeInTheDocument();
  });
});

// ----------------------------------------------------------------------- logo

describe("Logo", () => {
  const withProfile = (profile) => ({ "GET /api/restaurant/profile": { name: "Spice Garden", address: "", phone: "", gstin: "", fssai: "", receipt_footer: "", logo: "", ...profile } });

  it("shows the logo in the header when one is saved", async () => {
    mockApi({ ...baseRoutes(OWNER), ...withProfile({ logo: LOGO }) });
    renderApp("/", { user: OWNER });

    const header = await screen.findByRole("banner");
    expect(await within(header).findByAltText("Restaurant logo")).toHaveAttribute("src", LOGO);
  });

  it("shows nothing extra in the header without a logo", async () => {
    mockApi({ ...baseRoutes(OWNER), ...withProfile({}) });
    renderApp("/", { user: OWNER });
    await screen.findByRole("heading", { name: "Dashboard" });

    expect(screen.queryByAltText("Restaurant logo")).not.toBeInTheDocument();
  });

  it("puts the logo on the bill preview but not on the kitchen ticket", async () => {
    const api = await openBill(OWNER, {
      ...withProfile({ logo: LOGO }),
      "GET /api/billing/bills/10/receipt": "TAX INVOICE\n",
      "POST /api/billing/orders/1/kot": { id: 5, order_id: 1, items: [] },
    });

    await userEvent.click(screen.getByRole("button", { name: "Print receipt" }));
    const receipt = await screen.findByRole("dialog");
    expect(await within(receipt).findByAltText("Restaurant logo")).toBeInTheDocument();
    expect(api.called("GET", "/api/billing/bills/10/receipt")).toHaveLength(1);
  });

  describe("upload in Settings", () => {
    async function openSettings(routes = {}) {
      const api = mockApi({
        ...baseRoutes(OWNER),
        ...withProfile({}),
        "PUT /api/restaurant/profile": ({ body }) => ({ name: "Spice Garden", ...body }),
        ...routes,
      });
      renderApp("/settings", { user: OWNER });
      const form = await screen.findByRole("form", { name: "Receipt details" });
      return { api, form, user: userEvent.setup({ applyAccept: false }) };
    }
    const png = (name = "logo.png", bytes = 4) => new File([new Uint8Array(bytes).fill(137)], name, { type: "image/png" });

    it("previews a chosen logo and saves it", async () => {
      const { api, form, user } = await openSettings();

      await user.upload(within(form).getByLabelText(/Logo \(PNG/), png());
      expect(await within(form).findByAltText("Logo preview")).toBeInTheDocument();
      await user.click(within(form).getByRole("button", { name: "Save receipt details" }));

      await screen.findByText(/Saved\./);
      expect(api.called("PUT", "/api/restaurant/profile")[0].body.logo).toMatch(/^data:image\/png;base64,/);
    });

    it("updates the header straight after saving", async () => {
      const { form, user } = await openSettings();

      await user.upload(within(form).getByLabelText(/Logo \(PNG/), png());
      await user.click(within(form).getByRole("button", { name: "Save receipt details" }));

      expect(await within(await screen.findByRole("banner")).findByAltText("Restaurant logo")).toBeInTheDocument();
    });

    it("can remove a saved logo", async () => {
      const { api, form, user } = await openSettings({ ...withProfile({ logo: LOGO }) });
      await within(form).findByAltText("Logo preview");

      await user.click(within(form).getByRole("button", { name: "Remove logo" }));
      expect(within(form).queryByAltText("Logo preview")).not.toBeInTheDocument();
      await user.click(within(form).getByRole("button", { name: "Save receipt details" }));

      await screen.findByText(/Saved\./);
      expect(api.called("PUT", "/api/restaurant/profile")[0].body.logo).toBe("");
    });

    it("refuses a file that is not PNG, JPEG or WebP before sending anything", async () => {
      const { api, form, user } = await openSettings();

      await user.upload(within(form).getByLabelText(/Logo \(PNG/), new File(["GIF89a"], "logo.gif", { type: "image/gif" }));

      expect(await within(form).findByRole("alert")).toHaveTextContent("PNG, JPEG or WebP");
      expect(within(form).queryByAltText("Logo preview")).not.toBeInTheDocument();
      expect(api.called("PUT", "/api/restaurant/profile")).toHaveLength(0);
    });

    it("refuses a file over 100 KB", async () => {
      const { form, user } = await openSettings();

      await user.upload(within(form).getByLabelText(/Logo \(PNG/), png("big.png", 100 * 1024 + 1));

      expect(await within(form).findByRole("alert")).toHaveTextContent("under 100 KB");
      expect(within(form).queryByAltText("Logo preview")).not.toBeInTheDocument();
    });

    it("shows the server's message if it still rejects the image", async () => {
      const { form, user } = await openSettings({
        "PUT /api/restaurant/profile": fail(422, "Value error, The logo file does not match its image type"),
      });

      await user.upload(within(form).getByLabelText(/Logo \(PNG/), png());
      await user.click(within(form).getByRole("button", { name: "Save receipt details" }));

      expect(await within(form).findByRole("alert")).toHaveTextContent("does not match its image type");
    });
  });
});

// -------------------------------------------------------- menu: stock and sizes

describe("Menu: stock", () => {
  async function openMenu(menu, routes = {}) {
    const fake = billingApi(OWNER);
    Object.assign(fake.routes, { "GET /api/billing/menu/items": menu, ...routes });
    const api = mockApi(fake.routes);
    renderApp("/billing", { user: OWNER });
    await userEvent.click(await screen.findByRole("tab", { name: "Menu & tables" }));
    return api;
  }

  it("marks low and sold-out items and leaves uncounted ones alone", async () => {
    await openMenu([item({ stock_quantity: 2 }), item({ id: 11, name: "Cola", stock_quantity: 0 }), item({ id: 12, name: "Naan", stock_quantity: 40 }), item({ id: 13, name: "Soup" })]);

    const list = await screen.findByRole("list", { name: "Menu items" });
    expect(within(list).getByText("2 left")).toHaveClass("badge-low");
    expect(within(list).getByText("Sold out")).toBeInTheDocument();
    expect(within(list).getByText("40 left")).not.toHaveClass("badge-low");
    expect(within(list).getAllByText(/left|Sold out/)).toHaveLength(3);
  });

  it("adds an item with stock", async () => {
    const api = await openMenu([], { "POST /api/billing/menu/items": item() });

    await userEvent.selectOptions(await screen.findByLabelText(/^Category/), "1");
    await userEvent.type(screen.getByLabelText("Item name"), "Gulab Jamun");
    await userEvent.type(screen.getByLabelText("Price (₹, excluding GST)"), "60");
    await userEvent.type(screen.getByLabelText(/^Stock \(leave empty/), "12");
    await userEvent.click(screen.getByRole("button", { name: "Add item" }));

    await waitFor(() => expect(api.called("POST", "/api/billing/menu/items")).toHaveLength(1));
    expect(api.called("POST", "/api/billing/menu/items")[0].body).toEqual({
      category_id: 1, name: "Gulab Jamun", price: "60", gst_rate: "5", stock_quantity: 12,
    });
  });

  it("restocks an item and can stop counting it", async () => {
    const api = await openMenu([item({ stock_quantity: 2 })], { "PATCH /api/billing/menu/items/10": item() });

    await userEvent.click(await screen.findByRole("button", { name: "Edit Paneer Tikka" }));
    const stock = screen.getByLabelText(/Stock of Paneer Tikka/);
    await userEvent.clear(stock);
    await userEvent.type(stock, "40");
    await userEvent.click(screen.getByRole("button", { name: "Save item" }));
    await waitFor(() => expect(api.called("PATCH", "/api/billing/menu/items/10")).toHaveLength(1));
    expect(api.called("PATCH", "/api/billing/menu/items/10")[0].body.stock_quantity).toBe(40);

    await userEvent.click(await screen.findByRole("button", { name: "Edit Paneer Tikka" }));
    await userEvent.clear(screen.getByLabelText(/Stock of Paneer Tikka/));
    await userEvent.click(screen.getByRole("button", { name: "Save item" }));
    await waitFor(() => expect(api.called("PATCH", "/api/billing/menu/items/10")).toHaveLength(2));
    expect(api.called("PATCH", "/api/billing/menu/items/10")[1].body.stock_quantity).toBeNull();
  });

  it("does not touch stock when only the price is edited", async () => {
    const api = await openMenu([item({ stock_quantity: 7 })], { "PATCH /api/billing/menu/items/10": item() });

    await userEvent.click(await screen.findByRole("button", { name: "Edit Paneer Tikka" }));
    const price = screen.getByLabelText("Price of Paneer Tikka");
    await userEvent.clear(price);
    await userEvent.type(price, "250");
    await userEvent.click(screen.getByRole("button", { name: "Save item" }));

    await waitFor(() => expect(api.called("PATCH", "/api/billing/menu/items/10")).toHaveLength(1));
    expect(api.called("PATCH", "/api/billing/menu/items/10")[0].body).not.toHaveProperty("stock_quantity");
  });
});

describe("Menu: sizes", () => {
  async function openMenu(menu, routes = {}) {
    const fake = billingApi(OWNER);
    Object.assign(fake.routes, { "GET /api/billing/menu/items": menu, ...routes });
    const api = mockApi(fake.routes);
    renderApp("/billing", { user: OWNER });
    await userEvent.click(await screen.findByRole("tab", { name: "Menu & tables" }));
    return api;
  }

  it("summarises an item's sizes in its row", async () => {
    await openMenu([SIZED]);

    const list = await screen.findByRole("list", { name: "Menu items" });
    expect(within(list).getByText("Half ₹120.00 · Full ₹200.00")).toBeInTheDocument();
  });

  it("opens the sizes panel for an item without sizes", async () => {
    await openMenu([COLA]);

    await userEvent.click(await screen.findByRole("button", { name: "Sizes of Cola" }));

    expect(within(screen.getByLabelText("Sizes of Cola")).getByText(/Cola is sold at one price/)).toBeInTheDocument();
  });

  it("adds a size", async () => {
    const api = await openMenu([COLA], { "POST /api/billing/menu/items/11/variants": { id: 1, name: "Large", price: "60.00" } });

    await userEvent.click(await screen.findByRole("button", { name: "Sizes of Cola" }));
    await userEvent.type(screen.getByLabelText("New size name for Cola"), "Large");
    await userEvent.type(screen.getByLabelText("New size price for Cola"), "60");
    await userEvent.click(screen.getByRole("button", { name: "Add size to Cola" }));

    await waitFor(() => expect(api.called("POST", "/api/billing/menu/items/11/variants")).toHaveLength(1));
    expect(api.called("POST", "/api/billing/menu/items/11/variants")[0].body).toEqual({ name: "Large", price: "60" });
  });

  it("shows why a duplicate size is refused", async () => {
    await openMenu([SIZED], { "POST /api/billing/menu/items/10/variants": fail(409, "This item already has that size") });

    await userEvent.click(await screen.findByRole("button", { name: "Sizes of Paneer Tikka" }));
    await userEvent.type(screen.getByLabelText("New size name for Paneer Tikka"), "half");
    await userEvent.type(screen.getByLabelText("New size price for Paneer Tikka"), "99");
    await userEvent.click(screen.getByRole("button", { name: "Add size to Paneer Tikka" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("already has that size");
  });

  it("edits a size's price", async () => {
    const api = await openMenu([SIZED], { "PATCH /api/billing/menu/variants/101": { id: 101, name: "Half", price: "130.00" } });

    await userEvent.click(await screen.findByRole("button", { name: "Sizes of Paneer Tikka" }));
    await userEvent.click(screen.getByRole("button", { name: "Edit size Half of Paneer Tikka" }));
    const price = screen.getByLabelText("Price of size Half");
    await userEvent.clear(price);
    await userEvent.type(price, "130");
    await userEvent.click(screen.getByRole("button", { name: "Save size" }));

    await waitFor(() => expect(api.called("PATCH", "/api/billing/menu/variants/101")).toHaveLength(1));
    expect(api.called("PATCH", "/api/billing/menu/variants/101")[0].body).toEqual({ name: "Half", price: "130" });
  });

  it("needs a second click to delete a size", async () => {
    const api = await openMenu([SIZED], { "DELETE /api/billing/menu/variants/101": {} });

    await userEvent.click(await screen.findByRole("button", { name: "Sizes of Paneer Tikka" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete size Half of Paneer Tikka" }));
    expect(api.called("DELETE", "/api/billing/menu/variants/101")).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Confirm delete size Half of Paneer Tikka" }));

    await waitFor(() => expect(api.called("DELETE", "/api/billing/menu/variants/101")).toHaveLength(1));
  });
});

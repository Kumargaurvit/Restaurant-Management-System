import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { billingApi } from "./test/fakeBilling.js";
import { CASHIER, OWNER, baseRoutes, fail, mockApi, renderApp } from "./test/helpers.jsx";

const MANAGER = { id: 4, name: "Mira", email: "mira@test.com", role: "manager" };
const PROFILE = {
  name: "Spice Route", address: "12 CP, Delhi", phone: "011 4000 1234",
  gstin: "07AAAAA0000A1Z5", fssai: "12345678901234", receipt_footer: "Thanks!",
};
const DETAILS_URL = "/api/restaurant/profile";
const STAFF = [
  { id: 1, name: "Asha", email: "asha@test.com", role: "owner", is_active: true },
  { id: 2, name: "Ravi", email: "ravi@test.com", role: "waiter", is_active: true },
  { id: 3, name: "Old Hand", email: "old@test.com", role: "cashier", is_active: false },
];

describe("Receipt details", () => {
  async function openSettings(user, routes = {}) {
    const api = mockApi({
      ...baseRoutes(user),
      [`GET ${DETAILS_URL}`]: PROFILE,
      "GET /api/auth/users": STAFF,
      ...routes,
    });
    renderApp("/settings", { user });
    return api;
  }

  it("loads the saved details into the form", async () => {
    await openSettings(OWNER);

    const form = await screen.findByRole("form", { name: "Receipt details" });
    expect(within(form).getByLabelText("Address")).toHaveValue("12 CP, Delhi");
    expect(within(form).getByLabelText("GSTIN")).toHaveValue("07AAAAA0000A1Z5");
    expect(within(form).getByLabelText("FSSAI licence number")).toHaveValue("12345678901234");
  });

  it("does not include the restaurant name, which has its own card", async () => {
    await openSettings(OWNER);

    const form = await screen.findByRole("form", { name: "Receipt details" });
    expect(within(form).queryByLabelText("Restaurant name")).not.toBeInTheDocument();
    expect(screen.getByRole("form", { name: "Restaurant name" })).toBeInTheDocument();
  });

  it("saves changes and confirms", async () => {
    const api = await openSettings(OWNER, { [`PUT ${DETAILS_URL}`]: ({ body }) => body });
    const address = await screen.findByLabelText("Address");

    await userEvent.clear(address);
    await userEvent.type(address, "7 Khan Market, Delhi");
    await userEvent.click(screen.getByRole("button", { name: "Save receipt details" }));

    expect(await screen.findByText(/Saved\. New receipts will use these details/)).toBeInTheDocument();
    expect(api.called("PUT", DETAILS_URL)[0].body).toEqual({
      address: "7 Khan Market, Delhi",
      phone: "011 4000 1234",
      gstin: "07AAAAA0000A1Z5",
      fssai: "12345678901234",
      receipt_footer: "Thanks!",
    });
  });

  it("shows the server's message for an invalid GSTIN", async () => {
    await openSettings(OWNER, {
      [`PUT ${DETAILS_URL}`]: fail(422, "Value error, GSTIN must be 15 characters, like 07AAAAA0000A1Z5"),
    });
    await screen.findByLabelText("GSTIN");

    await userEvent.click(screen.getByRole("button", { name: "Save receipt details" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("GSTIN must be 15 characters");
  });

  it("is available to a manager, who cannot rename the restaurant", async () => {
    await openSettings(MANAGER);

    expect(await screen.findByRole("form", { name: "Receipt details" })).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Restaurant name" })).not.toBeInTheDocument();
  });

  it("is hidden from a cashier", async () => {
    await openSettings(CASHIER);
    await screen.findByRole("heading", { name: "Settings" });

    expect(screen.queryByRole("form", { name: "Receipt details" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Staff" })).not.toBeInTheDocument();
  });
});

describe("Staff management", () => {
  async function openStaff(routes = {}) {
    const api = mockApi({
      ...baseRoutes(OWNER),
      [`GET ${DETAILS_URL}`]: PROFILE,
      "GET /api/auth/users": STAFF,
      ...routes,
    });
    renderApp("/settings", { user: OWNER });
    const list = await screen.findByRole("list", { name: "Staff members" });
    return { api, list };
  }

  it("is only shown to the owner", async () => {
    mockApi({ ...baseRoutes(MANAGER), [`GET ${DETAILS_URL}`]: PROFILE });
    renderApp("/settings", { user: MANAGER });
    await screen.findByRole("form", { name: "Receipt details" });

    expect(screen.queryByRole("region", { name: "Staff" })).not.toBeInTheDocument();
  });

  it("lists staff with roles and marks inactive and current users", async () => {
    const { list } = await openStaff();

    expect(within(list).getByText("(you)")).toBeInTheDocument();
    expect(within(list).getByText("Inactive")).toBeInTheDocument();
    expect(within(list).getByLabelText("Role for Ravi")).toHaveValue("waiter");
    expect(within(list).getByRole("button", { name: "Reactivate" })).toBeInTheDocument();
  });

  it("changes a role", async () => {
    const { api } = await openStaff({ "PATCH /api/auth/users/2": { ...STAFF[1], role: "cashier" } });

    await userEvent.selectOptions(screen.getByLabelText("Role for Ravi"), "cashier");

    await waitFor(() =>
      expect(api.called("PATCH", "/api/auth/users/2")[0].body).toEqual({ role: "cashier" }),
    );
  });

  it("deactivates and reactivates staff", async () => {
    const { api, list } = await openStaff({
      "PATCH /api/auth/users/2": STAFF[1],
      "PATCH /api/auth/users/3": STAFF[2],
    });
    const ravi = within(list).getByText("Ravi").closest("li");

    await userEvent.click(within(ravi).getByRole("button", { name: "Deactivate" }));
    await userEvent.click(within(list).getByRole("button", { name: "Reactivate" }));

    await waitFor(() => expect(api.called("PATCH", "/api/auth/users/2")[0].body).toEqual({ is_active: false }));
    await waitFor(() => expect(api.called("PATCH", "/api/auth/users/3")[0].body).toEqual({ is_active: true }));
  });

  it("shows the server's message when a change is refused", async () => {
    await openStaff({ "PATCH /api/auth/users/1": fail(409, "You cannot deactivate yourself") });
    const asha = within(screen.getByRole("list", { name: "Staff members" })).getByText("Asha").closest("li");

    await userEvent.click(within(asha).getByRole("button", { name: "Deactivate" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("You cannot deactivate yourself");
  });

  it("adds a staff member", async () => {
    const { api } = await openStaff({ "POST /api/auth/users": { id: 9 } });
    const form = screen.getByRole("form", { name: "Add staff" });

    await userEvent.type(within(form).getByLabelText("Name"), "Neha");
    await userEvent.type(within(form).getByLabelText("Email"), "neha@test.com");
    await userEvent.type(within(form).getByLabelText(/Password/), "password123");
    await userEvent.selectOptions(within(form).getByLabelText("Role"), "cashier");
    await userEvent.click(within(form).getByRole("button", { name: "Add staff member" }));

    expect(await screen.findByText("Staff member added.")).toBeInTheDocument();
    expect(api.called("POST", "/api/auth/users")[0].body).toEqual({
      name: "Neha", email: "neha@test.com", password: "password123", role: "cashier",
    });
  });

  it("resets a password", async () => {
    const { api, list } = await openStaff({ "POST /api/auth/users/2/password": {} });
    const ravi = within(list).getByText("Ravi").closest("li");

    await userEvent.click(within(ravi).getByRole("button", { name: "Reset password" }));
    const form = screen.getByRole("form", { name: "Reset password" });
    await userEvent.type(within(form).getByLabelText(/New password for Ravi/), "a-new-password");
    await userEvent.click(within(form).getByRole("button", { name: "Change password" }));

    expect(await screen.findByText("Password changed.")).toBeInTheDocument();
    expect(api.called("POST", "/api/auth/users/2/password")[0].body).toEqual({ password: "a-new-password" });
  });
});

describe("Editing the menu and tables", () => {
  async function openMenu(routes = {}) {
    const fake = billingApi(OWNER);
    Object.assign(fake.routes, routes);
    const api = mockApi(fake.routes);
    renderApp("/billing", { user: OWNER });
    await userEvent.click(await screen.findByRole("tab", { name: "Menu & tables" }));
    return api;
  }

  it("renames a category", async () => {
    const api = await openMenu({ "PATCH /api/billing/menu/categories/1": { id: 1, name: "Main Course", sort_order: 0 } });

    await userEvent.click(await screen.findByRole("button", { name: "Rename Mains" }));
    const name = screen.getByLabelText("Category name Mains");
    await userEvent.clear(name);
    await userEvent.type(name, "Main Course");
    await userEvent.click(screen.getByRole("button", { name: "Save category" }));

    await waitFor(() =>
      expect(api.called("PATCH", "/api/billing/menu/categories/1")[0].body).toEqual({ name: "Main Course" }),
    );
  });

  it("edits a menu item's name, price, GST and category", async () => {
    const api = await openMenu({ "PATCH /api/billing/menu/items/11": { id: 11 } });

    await userEvent.click(await screen.findByRole("button", { name: "Edit Cola" }));
    const price = screen.getByLabelText("Price of Cola");
    await userEvent.clear(price);
    await userEvent.type(price, "60");
    await userEvent.selectOptions(screen.getByLabelText("GST of Cola"), "12");
    await userEvent.click(screen.getByRole("button", { name: "Save item" }));

    await waitFor(() =>
      expect(api.called("PATCH", "/api/billing/menu/items/11")[0].body).toEqual({
        name: "Cola", price: "60", gst_rate: "12", category_id: 1,
      }),
    );
  });

  it("needs a second click to delete an item, and can be cancelled", async () => {
    const api = await openMenu({ "DELETE /api/billing/menu/items/11": {} });

    await userEvent.click(await screen.findByRole("button", { name: "Delete Cola" }));
    expect(api.called("DELETE", "/api/billing/menu/items/11")).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Keep" }));
    expect(screen.getByRole("button", { name: "Delete Cola" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Delete Cola" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm delete Cola" }));

    await waitFor(() => expect(api.called("DELETE", "/api/billing/menu/items/11")).toHaveLength(1));
  });

  it("shows why an ordered item cannot be deleted", async () => {
    await openMenu({
      "DELETE /api/billing/menu/items/10": fail(409, "This item has been ordered before. Mark it unavailable instead."),
    });

    await userEvent.click(await screen.findByRole("button", { name: "Delete Paneer Tikka" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm delete Paneer Tikka" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Mark it unavailable instead");
  });

  it("shows why a category with items cannot be deleted", async () => {
    await openMenu({
      "DELETE /api/billing/menu/categories/1": fail(409, "Move or delete this category's items first"),
    });

    await userEvent.click(await screen.findByRole("button", { name: "Delete Mains" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm delete Mains" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Move or delete this category's items first");
  });

  it("edits a table", async () => {
    const api = await openMenu({ "PATCH /api/billing/tables/1": { id: 1 } });

    await userEvent.click(await screen.findByRole("button", { name: "Edit table T1" }));
    const seats = screen.getByLabelText("Seats at table T1");
    await userEvent.clear(seats);
    await userEvent.type(seats, "8");
    await userEvent.click(screen.getByRole("button", { name: "Save table" }));

    await waitFor(() =>
      expect(api.called("PATCH", "/api/billing/tables/1")[0].body).toEqual({ name: "T1", capacity: 8 }),
    );
  });

  it("deactivates a table and deletes one", async () => {
    const api = await openMenu({
      "PATCH /api/billing/tables/2": { id: 2 },
      "DELETE /api/billing/tables/2": {},
    });

    await userEvent.click(await screen.findByRole("button", { name: "Deactivate T2" }));
    await userEvent.click(screen.getByRole("button", { name: "Delete table T2" }));
    await userEvent.click(screen.getByRole("button", { name: "Confirm delete table T2" }));

    await waitFor(() => expect(api.called("PATCH", "/api/billing/tables/2")[0].body).toEqual({ is_active: false }));
    await waitFor(() => expect(api.called("DELETE", "/api/billing/tables/2")).toHaveLength(1));
  });

  it("shows when a table has an open order", async () => {
    await openMenu({ "PATCH /api/billing/tables/1": fail(409, "Table has an open order") });

    await userEvent.click(await screen.findByRole("button", { name: "Deactivate T1" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Table has an open order");
  });
});

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { CASHIER, OWNER, baseRoutes, mockApi, renderApp } from "./test/helpers.jsx";

const booking = {
  id: 7,
  guest_name: "Neha",
  phone: "9876543210",
  party_size: 2,
  booking_date: "2026-11-01",
  start_time: "12:30:00",
  end_time: "14:00:00",
  slot_minutes: 90,
  status: "requested",
  source: "staff",
  notes: null,
};

const slots = [
  { start_time: "11:00:00", available: true },
  { start_time: "12:30:00", available: false },
  { start_time: "14:00:00", available: true },
];

const routes = (user, overrides = {}) => ({
  ...baseRoutes(user),
  "GET /api/bookings": [booking],
  "GET /api/bookings/availability": { booking_date: "2026-11-01", party_size: 2, slots },
  "GET /api/bookings/settings": {
    opens_at: "11:00:00",
    closes_at: "23:00:00",
    slot_minutes: 90,
    max_party_size: 12,
    max_days_ahead: 30,
    reminder_hours_before: 3,
  },
  ...overrides,
});

describe("Bookings page", () => {
  it("lists the day's bookings with their status", async () => {
    mockApi(routes(OWNER));
    renderApp("/bookings", { user: OWNER });

    const list = await screen.findByRole("list", { name: "Bookings" });
    expect(within(list).getByText(/Neha/)).toBeInTheDocument();
    expect(within(list).getByText("requested")).toBeInTheDocument();
  });

  it("confirms a requested booking", async () => {
    const api = mockApi(
      routes(OWNER, { "POST /api/bookings/7/status": { ...booking, status: "confirmed" } }),
    );
    renderApp("/bookings", { user: OWNER });

    await userEvent.click(await screen.findByRole("button", { name: "Confirm Neha" }));

    await waitFor(() => expect(api.called("POST", "/api/bookings/7/status")).toHaveLength(1));
    expect(api.called("POST", "/api/bookings/7/status")[0].body).toEqual({ status: "confirmed" });
  });

  it("only offers the free slots when making a booking", async () => {
    mockApi(routes(OWNER));
    renderApp("/bookings", { user: OWNER });

    const form = await screen.findByRole("region", { name: "New booking" });
    const time = await within(form).findByRole("combobox", { name: "Time" });
    await waitFor(() => expect(within(time).getAllByRole("option")).toHaveLength(3));
    expect(within(time).queryByRole("option", { name: "12:30" })).not.toBeInTheDocument();
    expect(within(time).getByRole("option", { name: "14:00" })).toBeInTheDocument();
  });

  it("shows the error when a booking is rejected", async () => {
    mockApi(
      routes(OWNER, {
        "POST /api/bookings": () => ({ __error: true, status: 409, body: { detail: "No table is free for that slot." } }),
      }),
    );
    renderApp("/bookings", { user: OWNER });

    const form = await screen.findByRole("region", { name: "New booking" });
    await userEvent.type(within(form).getByLabelText("Guest name"), "Ravi");
    await userEvent.type(within(form).getByLabelText("Mobile number"), "9811111111");
    await userEvent.selectOptions(await within(form).findByLabelText("Time"), "14:00:00");
    await userEvent.click(within(form).getByRole("button", { name: "Book table" }));

    expect(await within(form).findByRole("alert")).toHaveTextContent("No table is free for that slot.");
  });

  it("shows hours and slots settings to managers only", async () => {
    mockApi(routes(OWNER));
    renderApp("/bookings", { user: OWNER });
    expect(await screen.findByRole("tab", { name: "Hours & slots" })).toBeInTheDocument();
  });

  it("hides the settings tab from a cashier", async () => {
    mockApi(routes(CASHIER));
    renderApp("/bookings", { user: CASHIER });

    await screen.findByRole("list", { name: "Bookings" });
    expect(screen.queryByRole("tab", { name: "Hours & slots" })).not.toBeInTheDocument();
  });

  it("saves booking settings", async () => {
    const api = mockApi(routes(OWNER, { "PUT /api/bookings/settings": {} }));
    renderApp("/bookings", { user: OWNER });

    await userEvent.click(await screen.findByRole("tab", { name: "Hours & slots" }));
    const slot = await screen.findByLabelText("Slot length (minutes)");
    await userEvent.clear(slot);
    await userEvent.type(slot, "60");
    await userEvent.click(screen.getByRole("button", { name: "Save settings" }));

    await waitFor(() => expect(api.called("PUT", "/api/bookings/settings")).toHaveLength(1));
    expect(api.called("PUT", "/api/bookings/settings")[0].body).toMatchObject({
      slot_minutes: 60,
      opens_at: "11:00",
    });
  });
});

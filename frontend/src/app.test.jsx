import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { MODULES } from "./modules.js";
import { OWNER, baseRoutes, fail, mockApi, renderApp } from "./test/helpers.jsx";

describe("Dashboard", () => {
  it("shows Online when the backend health check passes", async () => {
    mockApi(baseRoutes(OWNER));
    renderApp("/", { user: OWNER });

    expect(await screen.findByText("Online")).toBeInTheDocument();
  });

  it("shows Offline when the backend cannot be reached", async () => {
    mockApi({ ...baseRoutes(OWNER), "GET /health": fail(503, "down") });
    renderApp("/", { user: OWNER });

    expect(await screen.findByText("Offline")).toBeInTheDocument();
  });

  it("re-checks the backend when Check again is clicked", async () => {
    const api = mockApi(baseRoutes(OWNER));
    renderApp("/", { user: OWNER });
    await screen.findByText("Online");

    await userEvent.click(screen.getByRole("button", { name: "Check again" }));

    await waitFor(() => expect(api.called("GET", "/health")).toHaveLength(2));
  });

  it("lists every module as a card that links to its page", async () => {
    mockApi(baseRoutes(OWNER));
    renderApp("/", { user: OWNER });
    await screen.findByText("Online");

    const content = screen.getByRole("main");
    for (const module of MODULES) {
      const link = within(content).getByRole("link", { name: new RegExp(module.name) });
      expect(link).toHaveAttribute("href", `/${module.path}`);
    }
  });

  it("marks every finished module as live", async () => {
    mockApi(baseRoutes(OWNER));
    renderApp("/", { user: OWNER });
    await screen.findByText("Online");

    const content = screen.getByRole("main");
    expect(within(content).getByRole("link", { name: /Billing/ })).toHaveTextContent("Live");
    expect(within(content).getByRole("link", { name: /Bookings/ })).toHaveTextContent("Live");
    expect(within(content).getByRole("link", { name: /Retention/ })).toHaveTextContent("Live");
    expect(within(content).getByRole("link", { name: /WhatsApp Bot/ })).toHaveTextContent("Live");
  });
});

describe("Header", () => {
  it("shows the restaurant name after Restaurant Manager", async () => {
    const user = { ...OWNER, restaurant_name: "Spice Garden" };
    mockApi(baseRoutes(user));
    renderApp("/", { user });

    expect(await screen.findByText("Restaurant Manager - Spice Garden")).toBeInTheDocument();
  });

  it("shows just Restaurant Manager when no name is saved", async () => {
    mockApi(baseRoutes(OWNER));
    renderApp("/", { user: OWNER });

    expect(await screen.findByText("Restaurant Manager")).toBeInTheDocument();
  });
});

describe("Navigation", () => {
  it("has a sidebar link for every module plus Dashboard and Settings", async () => {
    mockApi(baseRoutes(OWNER));
    renderApp("/", { user: OWNER });
    await screen.findByRole("heading", { name: "Dashboard" });

    const nav = screen.getByRole("navigation");
    for (const module of MODULES) {
      expect(within(nav).getByRole("link", { name: module.name })).toBeInTheDocument();
    }
    expect(within(nav).getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Settings" })).toBeInTheDocument();
  });

  it("shows a not-found page for an unknown module", async () => {
    mockApi(baseRoutes(OWNER));
    renderApp("/does-not-exist", { user: OWNER });

    expect(await screen.findByRole("heading", { name: "Page not found" })).toBeInTheDocument();
  });

  it.each(MODULES.filter((module) => !module.live).map((m) => [m.path, m.name, m.stage]))(
    "shows the planned-stage placeholder for /%s",
    async (path, name, stage) => {
      mockApi(baseRoutes(OWNER));
      renderApp(`/${path}`, { user: OWNER });

      expect(await screen.findByRole("heading", { name })).toBeInTheDocument();
      expect(screen.getAllByText(new RegExp(`stage ${stage}`)).length).toBeGreaterThan(0);
    },
  );
});

describe("Settings", () => {
  it("shows the environment reported by the backend", async () => {
    mockApi({
      ...baseRoutes(OWNER),
      "GET /health": { status: "ok", environment: "staging" },
    });
    renderApp("/settings", { user: OWNER });

    expect(await screen.findByText("staging")).toBeInTheDocument();
  });

  it("shows an error when the backend is unreachable", async () => {
    mockApi({ ...baseRoutes(OWNER), "GET /health": fail(503, "down") });
    renderApp("/settings", { user: OWNER });

    expect(await screen.findByText("Could not reach the backend.")).toBeInTheDocument();
  });
});

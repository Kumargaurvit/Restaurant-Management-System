import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { OWNER, baseRoutes, fail, mockApi, renderApp } from "./test/helpers.jsx";

const TOKEN_RESPONSE = { access_token: "abc", token_type: "bearer", user: OWNER };

describe("Sign in", () => {
  it("shows the sign-in form when users already exist", async () => {
    mockApi({ "GET /api/auth/status": { has_users: true } });
    renderApp("/");

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Your name")).not.toBeInTheDocument();
  });

  it("signs in and lands on the dashboard", async () => {
    const api = mockApi({
      "GET /api/auth/status": { has_users: true },
      "POST /api/auth/login": TOKEN_RESPONSE,
      "GET /health": { status: "ok", environment: "development" },
    });
    renderApp("/");

    await userEvent.type(await screen.findByLabelText("Email"), "asha@test.com");
    await userEvent.type(screen.getByLabelText("Password"), "password123");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    expect(screen.getByText(/Asha/)).toBeInTheDocument();
    expect(api.called("POST", "/api/auth/login")[0].body).toEqual({
      email: "asha@test.com",
      password: "password123",
    });
    expect(localStorage.getItem("rms_token")).toBe("abc");
  });

  it("shows the server message when the password is wrong", async () => {
    mockApi({
      "GET /api/auth/status": { has_users: true },
      "POST /api/auth/login": fail(401, "Invalid email or password"),
    });
    renderApp("/");

    await userEvent.type(await screen.findByLabelText("Email"), "asha@test.com");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password");
    expect(screen.queryByRole("heading", { name: "Dashboard" })).not.toBeInTheDocument();
  });

  it("tells the user when the backend cannot be reached", async () => {
    mockApi({ "GET /api/auth/status": fail(500, "boom") });
    renderApp("/");

    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot reach the server");
  });
});

describe("First-time setup", () => {
  it("offers to create the owner account when no users exist", async () => {
    mockApi({ "GET /api/auth/status": { has_users: false } });
    renderApp("/");

    expect(await screen.findByRole("heading", { name: "Set up your restaurant" })).toBeInTheDocument();
    expect(screen.getByLabelText("Your name")).toBeInTheDocument();
    expect(screen.getByLabelText("Restaurant name")).toBeRequired();
  });

  it("creates the owner and signs in", async () => {
    const api = mockApi({
      "GET /api/auth/status": { has_users: false },
      "POST /api/auth/bootstrap": TOKEN_RESPONSE,
      "GET /health": { status: "ok", environment: "development" },
    });
    renderApp("/");

    await userEvent.type(await screen.findByLabelText("Restaurant name"), "Spice Garden");
    await userEvent.type(screen.getByLabelText("Your name"), "Asha");
    await userEvent.type(screen.getByLabelText("Email"), "asha@test.com");
    await userEvent.type(screen.getByLabelText("Password"), "password123");
    await userEvent.click(screen.getByRole("button", { name: "Create owner account" }));

    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    expect(api.called("POST", "/api/auth/bootstrap")[0].body).toMatchObject({
      name: "Asha",
      restaurant_name: "Spice Garden",
    });
  });
});

describe("Register or sign in", () => {
  it("lets a visitor switch between sign in and register", async () => {
    mockApi({ "GET /api/auth/status": { has_users: true } });
    renderApp("/");

    await userEvent.click(await screen.findByRole("button", { name: "New restaurant? Register" }));
    expect(screen.getByRole("heading", { name: "Register" })).toBeInTheDocument();
    expect(screen.getByLabelText("Restaurant name")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Already have an account? Sign in" }));
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Restaurant name")).not.toBeInTheDocument();
  });

  it("can switch to sign in before any owner exists", async () => {
    mockApi({ "GET /api/auth/status": { has_users: false } });
    renderApp("/");

    await userEvent.click(await screen.findByRole("button", { name: "Already have an account? Sign in" }));

    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });

  it("explains that registration is closed once an owner exists", async () => {
    mockApi({
      "GET /api/auth/status": { has_users: true },
      "POST /api/auth/bootstrap": fail(409, "Setup already completed"),
    });
    renderApp("/");

    await userEvent.click(await screen.findByRole("button", { name: "New restaurant? Register" }));
    expect(screen.getByText(/Only the first owner can register/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Restaurant name"), "Spice Garden");
    await userEvent.type(screen.getByLabelText("Your name"), "Ravi");
    await userEvent.type(screen.getByLabelText("Email"), "ravi@test.com");
    await userEvent.type(screen.getByLabelText("Password"), "password123");
    await userEvent.click(screen.getByRole("button", { name: "Create owner account" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("An owner account already exists");
  });
});

describe("Saved session", () => {
  it("restores the user from a saved token", async () => {
    const api = mockApi(baseRoutes(OWNER));
    renderApp("/", { user: OWNER });

    expect(await screen.findByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
    expect(api.called("GET", "/api/auth/me")[0].headers.Authorization).toBe("Bearer test-token");
  });

  it("falls back to sign in when the saved token is rejected", async () => {
    mockApi({
      "GET /api/auth/me": fail(401, "Not authenticated"),
      "GET /api/auth/status": { has_users: true },
    });
    renderApp("/", { user: OWNER });

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(localStorage.getItem("rms_token")).toBeNull();
  });

  it("signs out and clears the token", async () => {
    mockApi({ ...baseRoutes(OWNER), "GET /api/auth/status": { has_users: true } });
    renderApp("/", { user: OWNER });
    await screen.findByRole("heading", { name: "Dashboard" });

    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));

    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    await waitFor(() => expect(localStorage.getItem("rms_token")).toBeNull());
  });
});

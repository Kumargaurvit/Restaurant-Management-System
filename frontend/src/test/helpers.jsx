import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import App from "../App.jsx";
import { AuthProvider } from "../auth.jsx";

export const OWNER = { id: 1, name: "Asha", email: "asha@test.com", role: "owner" };
export const WAITER = { id: 2, name: "Ravi", email: "ravi@test.com", role: "waiter" };
export const CASHIER = { id: 3, name: "Meena", email: "meena@test.com", role: "cashier" };

/** Mark a mocked response as an error. */
export const fail = (status, detail) => ({ __error: true, status, body: { detail } });

/**
 * Stub `fetch` with a route table keyed by "METHOD /path" (query string ignored).
 * A handler is a value or a function `({ body, path }) => value`.
 * Every request is recorded in `calls`.
 */
export function mockApi(routes) {
  const calls = [];

  const fetchMock = vi.fn(async (url, options = {}) => {
    const path = String(url).replace(/^https?:\/\/[^/]+/, "");
    const method = options.method ?? "GET";
    const body = options.body ? JSON.parse(options.body) : undefined;
    calls.push({ method, path, body, headers: options.headers ?? {} });

    const handler = routes[`${method} ${path}`] ?? routes[`${method} ${path.split("?")[0]}`];
    if (handler === undefined) {
      return response(404, { detail: `No mock for ${method} ${path}` });
    }
    const result = typeof handler === "function" ? handler({ body, path }) : handler;
    if (result?.__error) return response(result.status, result.body);
    return response(200, result);
  });

  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock, called: (method, path) => calls.filter((c) => c.method === method && c.path.split("?")[0] === path) };
}

function response(status, payload) {
  // Real responses are always fresh copies; cloning stops tests sharing object references.
  if (payload !== undefined && typeof payload !== "string") {
    payload = JSON.parse(JSON.stringify(payload));
  }
  return {
    ok: status < 400,
    status,
    json: async () => {
      if (typeof payload === "string") throw new SyntaxError("not json");
      return payload;
    },
    text: async () => (typeof payload === "string" ? payload : JSON.stringify(payload)),
  };
}

/** Render the whole app at a route, optionally already signed in. */
export function renderApp(route = "/", { user = null } = {}) {
  localStorage.clear();
  if (user) localStorage.setItem("rms_token", "test-token");
  return render(
    <MemoryRouter initialEntries={[route]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}

export const baseRoutes = (user) => ({
  "GET /api/auth/me": user,
  "GET /health": { status: "ok", environment: "development" },
});

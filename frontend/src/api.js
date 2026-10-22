export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

const TOKEN_KEY = "rms_token";

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token) {
  try {
    if (token) {
      localStorage.setItem(TOKEN_KEY, token);
    } else {
      localStorage.removeItem(TOKEN_KEY);
    }
  } catch {
    // Storage can be unavailable (private mode); the session then lasts until reload.
  }
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

function errorMessage(body, status) {
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map((entry) => entry.msg).join(", ");
  }
  return `Request failed (${status})`;
}

export async function request(path, { method = "GET", body, signal, as = "json" } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const response = await fetch(`${API_URL}${path}`, {
    method,
    headers,
    signal,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (!response.ok) {
    let parsed = null;
    try {
      parsed = await response.json();
    } catch {
      // Not a JSON error body.
    }
    throw new ApiError(errorMessage(parsed, response.status), response.status);
  }
  return as === "text" ? response.text() : response.json();
}

export function getHealth(signal) {
  return request("/health", { signal });
}

export function formatMoney(value) {
  const amount = Number(value);
  return `₹${(Number.isFinite(amount) ? amount : 0).toFixed(2)}`;
}

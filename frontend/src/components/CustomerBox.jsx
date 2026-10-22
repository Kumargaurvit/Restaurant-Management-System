import { useEffect, useState } from "react";
import { ApiError, request } from "../api.js";

const digitsOnly = (value) => value.replace(/\D/g, "");

// Attaches a guest (by mobile number) to an order so their visits and dishes are remembered.
export default function CustomerBox({ order, onOrderChange }) {
  const isOpen = order.status === "open";
  const [editing, setEditing] = useState(false);
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [known, setKnown] = useState(null); // lookup result for the typed number
  const [attached, setAttached] = useState(null); // lookup result for the order's customer
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  // Look up the customer already on the order, to show their visit count.
  useEffect(() => {
    setAttached(null);
    if (!order.customer_phone) return undefined;
    const controller = new AbortController();
    request(`/api/customers/lookup?phone=${encodeURIComponent(order.customer_phone)}`, {
      signal: controller.signal,
    })
      .then(setAttached)
      .catch(() => {});
    return () => controller.abort();
  }, [order.customer_phone]);

  // Recognise a returning guest as soon as a full number is typed.
  useEffect(() => {
    setKnown(null);
    const digits = digitsOnly(phone);
    if (digits.length < 10) return undefined;
    const controller = new AbortController();
    request(`/api/customers/lookup?phone=${encodeURIComponent(phone)}`, {
      signal: controller.signal,
    })
      .then((found) => {
        setKnown(found);
        setName((current) => current || found.name || "");
      })
      .catch((err) => {
        if (err.name === "AbortError") return;
        if (!(err instanceof ApiError && err.status === 404)) setError(err.message);
      });
    return () => controller.abort();
  }, [phone]);

  async function save(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const updated = await request(`/api/billing/orders/${order.id}/customer`, {
        method: "PUT",
        body: { phone, name: name || null },
      });
      onOrderChange(updated);
      setEditing(false);
      setPhone("");
      setName("");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const hasCustomer = Boolean(order.customer_id);

  if (hasCustomer && !editing) {
    return (
      <div className="customer-box" aria-label="Customer">
        <strong>{order.customer_name || "Guest"}</strong>
        <span className="muted"> {order.customer_phone}</span>
        {attached && (
          <span className={`badge ${attached.is_returning ? "badge-ok" : "badge-checking"}`}>
            {attached.is_returning ? `Returning · ${attached.visits} visits` : "New guest"}
          </span>
        )}
        {isOpen && (
          <button className="link-button" onClick={() => setEditing(true)}>
            Change
          </button>
        )}
      </div>
    );
  }

  if (!isOpen) return null;

  return (
    <form className="customer-box" onSubmit={save} aria-label="Add customer">
      <div className="row">
        <label>
          Guest mobile number
          <input
            inputMode="tel"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="98765 43210"
          />
        </label>
        <label>
          Name (optional)
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <button className="button secondary" type="submit" disabled={busy || phone.trim() === ""}>
          Save customer
        </button>
        {hasCustomer && (
          <button className="button secondary" type="button" onClick={() => setEditing(false)}>
            Cancel
          </button>
        )}
      </div>
      {known && (
        <p className="muted" role="status">
          {known.is_returning ? "Returning customer" : "Known guest"}: {known.name || "no name saved"},{" "}
          {known.visits} {known.visits === 1 ? "visit" : "visits"}.
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}

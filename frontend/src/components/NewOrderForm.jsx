import { useEffect, useState } from "react";
import { ApiError, request } from "../api.js";

const digitsOnly = (value) => value.replace(/\D/g, "");

// Starts a dine-in or takeaway order. The guest's name and mobile number are required, and an
// existing customer is recognised by number and their name is filled in automatically.
export default function NewOrderForm({ type, freeTables = [], initialTableId = "", onSubmit, onCancel }) {
  const isDineIn = type === "dine_in";
  const [tableId, setTableId] = useState(initialTableId ? String(initialTableId) : "");
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [autoFilled, setAutoFilled] = useState(false); // name came from a customer lookup
  const [found, setFound] = useState(null); // customer from the lookup
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  // Look the guest up on their own as soon as a full number has been typed.
  useEffect(() => {
    setFound(null);
    setNotFound(false);
    if (digitsOnly(phone).length < 10) {
      // The number was cleared or shortened: drop a name that was only filled in by the lookup.
      if (autoFilled) {
        setName("");
        setAutoFilled(false);
      }
      return undefined;
    }
    const controller = new AbortController();
    request(`/api/customers/lookup?phone=${encodeURIComponent(phone)}`, { signal: controller.signal })
      .then((customer) => {
        setFound(customer);
        if (customer.name) {
          setName(customer.name);
          setAutoFilled(true);
        }
      })
      .catch((err) => {
        if (err.name === "AbortError") return;
        if (err instanceof ApiError && err.status === 404) setNotFound(true);
        else setError(err.message);
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phone]);

  async function submit(event) {
    event.preventDefault();
    if (!name.trim() || !phone.trim()) {
      setError("Customer name and contact number are required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onSubmit({
        order_type: type,
        ...(isDineIn ? { table_id: Number(tableId) } : {}),
        customer_name: name.trim(),
        customer_phone: phone.trim(),
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const label = isDineIn ? "New dine-in order" : "New takeaway order";

  return (
    <form className="card" onSubmit={submit} aria-label={label}>
      <h3>{label}</h3>
      {isDineIn && (
        <label>
          Table
          <select value={tableId} onChange={(e) => setTableId(e.target.value)} required>
            <option value="">Choose a table</option>
            {freeTables.map((table) => (
              <option key={table.id} value={table.id}>
                {table.name} · {table.capacity} seats
              </option>
            ))}
          </select>
        </label>
      )}
      <label>
        Contact number
        <input
          inputMode="tel"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          placeholder="98765 43210"
          required
        />
      </label>
      {found && (
        <p className="muted" role="status">
          Existing customer: {found.name || "no name saved"}, {found.visits}{" "}
          {found.visits === 1 ? "visit" : "visits"}
          {found.is_returning ? " (returning guest)" : ""}.
        </p>
      )}
      {notFound && (
        <p className="muted" role="status">
          No customer with this number yet. Enter their name to add them.
        </p>
      )}
      <label>
        Customer name
        <input
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            setAutoFilled(false); // a name typed by hand is kept
          }}
          required
        />
      </label>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="row">
        <button className="button" type="submit" disabled={busy}>
          Start order
        </button>
        <button className="button secondary" type="button" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

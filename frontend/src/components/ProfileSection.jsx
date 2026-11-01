import { useEffect, useState } from "react";
import { request } from "../api.js";

const EMPTY = { address: "", phone: "", gstin: "", fssai: "", receipt_footer: "" };

// The restaurant name has its own card (owner only). These details print under it on receipts.
export default function ProfileSection() {
  const [details, setDetails] = useState(null);
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    request("/api/restaurant/profile", { signal: controller.signal })
      .then((loaded) =>
        setDetails({
          address: loaded.address ?? "",
          phone: loaded.phone ?? "",
          gstin: loaded.gstin ?? "",
          fssai: loaded.fssai ?? "",
          receipt_footer: loaded.receipt_footer ?? "",
        }),
      )
      .catch((err) => {
        if (err.name !== "AbortError") setError(err.message);
      });
    return () => controller.abort();
  }, []);

  const change = (field) => (event) => {
    setMessage(null);
    setDetails({ ...details, [field]: event.target.value });
  };

  async function save(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await request("/api/restaurant/profile", {
        method: "PUT",
        body: { ...EMPTY, ...details },
      });
      setDetails({ ...EMPTY, ...saved });
      setMessage("Saved. New receipts will use these details.");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (!details) {
    return error ? (
      <p className="error" role="alert">
        {error}
      </p>
    ) : (
      <p className="muted">Loading...</p>
    );
  }

  return (
    <form className="card stack" onSubmit={save} aria-label="Receipt details">
      <h2>Receipt details</h2>
      <p className="muted">Printed under the restaurant name on every bill.</p>
      <label>
        Address
        <input value={details.address} onChange={change("address")} />
      </label>
      <label>
        Phone
        <input value={details.phone} onChange={change("phone")} />
      </label>
      <label>
        GSTIN
        <input value={details.gstin} onChange={change("gstin")} placeholder="07AAAAA0000A1Z5" />
      </label>
      <label>
        FSSAI licence number
        <input value={details.fssai} onChange={change("fssai")} placeholder="14 digits" />
      </label>
      <label>
        Receipt footer
        <input
          value={details.receipt_footer}
          onChange={change("receipt_footer")}
          placeholder="Thank you! Visit again."
        />
      </label>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {message && <p role="status">{message}</p>}
      <div>
        <button className="button" type="submit" disabled={busy}>
          Save receipt details
        </button>
      </div>
    </form>
  );
}

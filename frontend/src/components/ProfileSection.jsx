import { useEffect, useState } from "react";
import { request } from "../api.js";

const EMPTY = { name: "", address: "", phone: "", gstin: "", fssai: "", receipt_footer: "" };

export default function ProfileSection() {
  const [profile, setProfile] = useState(null);
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    request("/api/restaurant", { signal: controller.signal })
      .then((loaded) => setProfile({ ...EMPTY, ...loaded }))
      .catch((err) => {
        if (err.name !== "AbortError") setError(err.message);
      });
    return () => controller.abort();
  }, []);

  const change = (field) => (event) => {
    setMessage(null);
    setProfile({ ...profile, [field]: event.target.value });
  };

  async function save(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      setProfile(await request("/api/restaurant", { method: "PUT", body: profile }));
      setMessage("Saved. New receipts will use these details.");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (!profile) {
    return error ? (
      <p className="error" role="alert">
        {error}
      </p>
    ) : (
      <p className="muted">Loading...</p>
    );
  }

  return (
    <form className="card stack" onSubmit={save} aria-label="Restaurant profile">
      <h2>Restaurant profile</h2>
      <p className="muted">Printed at the top of every receipt.</p>
      <label>
        Restaurant name
        <input value={profile.name} onChange={change("name")} />
      </label>
      <label>
        Address
        <input value={profile.address} onChange={change("address")} />
      </label>
      <label>
        Phone
        <input value={profile.phone} onChange={change("phone")} />
      </label>
      <label>
        GSTIN
        <input value={profile.gstin} onChange={change("gstin")} placeholder="07AAAAA0000A1Z5" />
      </label>
      <label>
        FSSAI licence number
        <input value={profile.fssai} onChange={change("fssai")} placeholder="14 digits" />
      </label>
      <label>
        Receipt footer
        <input
          value={profile.receipt_footer}
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
          Save profile
        </button>
      </div>
    </form>
  );
}

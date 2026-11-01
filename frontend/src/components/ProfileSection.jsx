import { useEffect, useState } from "react";
import { request } from "../api.js";
import { LOGO_EVENT } from "../useRestaurantLogo.js";

const EMPTY = { address: "", phone: "", gstin: "", fssai: "", receipt_footer: "", logo: "" };
const MAX_LOGO_BYTES = 100 * 1024;
const LOGO_TYPES = ["image/png", "image/jpeg", "image/webp"];

function readAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("Could not read that file"));
    reader.readAsDataURL(file);
  });
}

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
          logo: loaded.logo ?? "",
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

  async function chooseLogo(event) {
    const file = event.target.files?.[0];
    event.target.value = ""; // let the same file be picked again later
    if (!file) return;
    setMessage(null);
    if (!LOGO_TYPES.includes(file.type)) {
      setError("The logo must be a PNG, JPEG or WebP image.");
      return;
    }
    if (file.size > MAX_LOGO_BYTES) {
      setError("The logo is too large. Use an image under 100 KB.");
      return;
    }
    try {
      setError(null);
      setDetails({ ...details, logo: await readAsDataUrl(file) });
    } catch (err) {
      setError(err.message);
    }
  }

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
      window.dispatchEvent(new CustomEvent(LOGO_EVENT, { detail: saved.logo ?? "" }));
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

      <div className="stack">
        <label>
          Logo (PNG, JPEG or WebP, under 100 KB)
          <input type="file" accept={LOGO_TYPES.join(",")} onChange={chooseLogo} />
        </label>
        {details.logo && (
          <div className="row">
            <img className="logo-preview" src={details.logo} alt="Logo preview" />
            <button
              className="button secondary"
              type="button"
              onClick={() => {
                setMessage(null);
                setDetails({ ...details, logo: "" });
              }}
            >
              Remove logo
            </button>
          </div>
        )}
      </div>

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

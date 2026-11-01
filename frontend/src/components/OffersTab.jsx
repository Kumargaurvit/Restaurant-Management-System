import { useCallback, useEffect, useState } from "react";
import { request } from "../api.js";

const EMPTY = { title: "", description: "", discount_percent: "", valid_from: "", valid_until: "" };

// <input type="datetime-local"> uses local time without an offset; the API wants a full timestamp.
const toIso = (local) => (local ? new Date(local).toISOString() : null);
const toLocalInput = (iso) => {
  if (!iso) return "";
  const date = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
};
const show = (iso) => (iso ? new Date(iso).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : null);

const STATUS_BADGE = {
  active: "badge-ok",
  upcoming: "badge-checking",
  expired: "badge-error",
  paused: "badge-error",
};

export default function OffersTab() {
  const [offers, setOffers] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [editingId, setEditingId] = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      setOffers(await request("/api/offers"));
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const body = (overrides = {}) => ({
    title: form.title,
    description: form.description,
    discount_percent: form.discount_percent === "" ? null : form.discount_percent,
    valid_from: toIso(form.valid_from),
    valid_until: toIso(form.valid_until),
    is_active: true,
    ...overrides,
  });

  async function attempt(action) {
    setError(null);
    try {
      await action();
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  function save(event) {
    event.preventDefault();
    const existing = offers.find((o) => o.id === editingId);
    return attempt(async () => {
      if (editingId) {
        await request(`/api/offers/${editingId}`, {
          method: "PUT",
          body: body({ is_active: existing.is_active }),
        });
      } else {
        await request("/api/offers", { method: "POST", body: body() });
      }
      setForm(EMPTY);
      setEditingId(null);
    });
  }

  function startEdit(offer) {
    setEditingId(offer.id);
    setForm({
      title: offer.title,
      description: offer.description,
      discount_percent: offer.discount_percent === null ? "" : String(Number(offer.discount_percent)),
      valid_from: toLocalInput(offer.valid_from),
      valid_until: toLocalInput(offer.valid_until),
    });
  }

  const togglePaused = (offer) =>
    attempt(() =>
      request(`/api/offers/${offer.id}`, {
        method: "PUT",
        body: {
          title: offer.title,
          description: offer.description,
          discount_percent: offer.discount_percent,
          valid_from: offer.valid_from,
          valid_until: offer.valid_until,
          is_active: !offer.is_active,
        },
      }),
    );

  const remove = (offer) =>
    attempt(async () => {
      await request(`/api/offers/${offer.id}`, { method: "DELETE" });
      setConfirmDelete(null);
    });

  return (
    <div className="menu-layout">
      <section className="card">
        <h2>{editingId ? "Edit offer" : "New offer"}</h2>
        <p className="muted">
          The WhatsApp bot only quotes offers listed here. For a discount that changes over time
          (for example 15% for 2 hours, then 10%), create one offer per period with start and end
          times.
        </p>
        <form className="stack" onSubmit={save} aria-label="Offer form">
          <label>
            Title
            <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required />
          </label>
          <label>
            Details (shown to guests)
            <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </label>
          <label>
            Discount (%)
            <input
              inputMode="decimal"
              value={form.discount_percent}
              onChange={(e) => setForm({ ...form, discount_percent: e.target.value })}
              placeholder="Leave empty if not a percentage"
            />
          </label>
          <label>
            Starts (optional)
            <input
              type="datetime-local"
              value={form.valid_from}
              onChange={(e) => setForm({ ...form, valid_from: e.target.value })}
            />
          </label>
          <label>
            Ends (optional)
            <input
              type="datetime-local"
              value={form.valid_until}
              onChange={(e) => setForm({ ...form, valid_until: e.target.value })}
            />
          </label>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <div className="row">
            <button className="button" type="submit">
              {editingId ? "Save offer" : "Add offer"}
            </button>
            {editingId && (
              <button
                className="button secondary"
                type="button"
                onClick={() => {
                  setEditingId(null);
                  setForm(EMPTY);
                }}
              >
                Cancel
              </button>
            )}
          </div>
        </form>
      </section>

      <section className="card">
        <h2>Offers</h2>
        {offers === null ? (
          <p className="muted">Loading...</p>
        ) : offers.length === 0 ? (
          <p className="muted">No offers yet.</p>
        ) : (
          <ul className="lines" aria-label="Offers">
            {offers.map((offer) => (
              <li key={offer.id}>
                <span className="line-name">
                  <strong>{offer.title}</strong>
                  {offer.discount_percent !== null && ` · ${Number(offer.discount_percent)}% off`}
                  <span className={`badge ${STATUS_BADGE[offer.status]}`}>{offer.status}</span>
                  <br />
                  <span className="muted">
                    {offer.description}
                    {offer.valid_from && ` From ${show(offer.valid_from)}.`}
                    {offer.valid_until && ` Until ${show(offer.valid_until)}.`}
                  </span>
                </span>
                <button className="button secondary" onClick={() => startEdit(offer)}>
                  {`Edit ${offer.title}`}
                </button>
                <button className="button secondary" onClick={() => togglePaused(offer)}>
                  {offer.is_active ? `Pause ${offer.title}` : `Resume ${offer.title}`}
                </button>
                {confirmDelete === offer.id ? (
                  <>
                    <button className="button danger" onClick={() => remove(offer)}>
                      {`Confirm delete ${offer.title}`}
                    </button>
                    <button className="button secondary" onClick={() => setConfirmDelete(null)}>
                      Keep
                    </button>
                  </>
                ) : (
                  <button className="button secondary" onClick={() => setConfirmDelete(offer.id)}>
                    {`Delete ${offer.title}`}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

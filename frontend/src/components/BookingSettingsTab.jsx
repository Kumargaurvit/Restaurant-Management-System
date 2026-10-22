import { useEffect, useState } from "react";
import { request } from "../api.js";

const clock = (value) => value.slice(0, 5);

export default function BookingSettingsTab() {
  const [form, setForm] = useState(null);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);
  const [reminders, setReminders] = useState(null);

  useEffect(() => {
    request("/api/bookings/settings")
      .then((settings) =>
        setForm({ ...settings, opens_at: clock(settings.opens_at), closes_at: clock(settings.closes_at) }),
      )
      .catch((err) => setError(err.message));
  }, []);

  const change = (field) => (e) => {
    setSaved(false);
    setForm({ ...form, [field]: e.target.value });
  };

  async function save(event) {
    event.preventDefault();
    setError(null);
    try {
      await request("/api/bookings/settings", {
        method: "PUT",
        body: {
          opens_at: form.opens_at,
          closes_at: form.closes_at,
          slot_minutes: Number(form.slot_minutes),
          max_party_size: Number(form.max_party_size),
          max_days_ahead: Number(form.max_days_ahead),
          reminder_hours_before: Number(form.reminder_hours_before),
        },
      });
      setSaved(true);
    } catch (err) {
      setError(err.message);
    }
  }

  async function sendReminders() {
    setError(null);
    try {
      const result = await request("/api/bookings/send-reminders", { method: "POST" });
      setReminders(result.sent);
    } catch (err) {
      setError(err.message);
    }
  }

  if (!form) {
    return error ? (
      <p className="error" role="alert">
        {error}
      </p>
    ) : (
      <p className="muted">Loading...</p>
    );
  }

  return (
    <div className="menu-layout">
      <section className="card">
        <h2>Booking hours and slots</h2>
        <p className="muted">
          Tables come from Menu &amp; tables in Billing. Each slot holds one table for the slot length.
        </p>
        <form className="stack" onSubmit={save}>
          <label>
            Opens at
            <input type="time" value={form.opens_at} onChange={change("opens_at")} required />
          </label>
          <label>
            Closes at
            <input type="time" value={form.closes_at} onChange={change("closes_at")} required />
          </label>
          <label>
            Slot length (minutes)
            <input type="number" min="15" value={form.slot_minutes} onChange={change("slot_minutes")} required />
          </label>
          <label>
            Largest party we take
            <input type="number" min="1" value={form.max_party_size} onChange={change("max_party_size")} required />
          </label>
          <label>
            Book up to (days ahead)
            <input type="number" min="1" value={form.max_days_ahead} onChange={change("max_days_ahead")} required />
          </label>
          <label>
            Send reminder (hours before)
            <input
              type="number"
              min="1"
              value={form.reminder_hours_before}
              onChange={change("reminder_hours_before")}
              required
            />
          </label>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          {saved && <p role="status">Settings saved.</p>}
          <button className="button" type="submit">
            Save settings
          </button>
        </form>
      </section>

      <section className="card">
        <h2>Reminders</h2>
        <p className="muted">Reminders go out automatically. You can also send the due ones now.</p>
        <button className="button secondary" onClick={sendReminders}>
          Send due reminders
        </button>
        {reminders !== null && <p role="status">{reminders} reminder(s) sent.</p>}
      </section>
    </div>
  );
}

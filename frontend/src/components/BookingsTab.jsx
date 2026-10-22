import { useCallback, useEffect, useState } from "react";
import { request } from "../api.js";

const todayInput = () => new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD
const clock = (value) => value.slice(0, 5);

// Mirrors the backend's allowed status changes.
const NEXT = {
  requested: [
    ["confirmed", "Confirm"],
    ["cancelled", "Cancel"],
  ],
  confirmed: [
    ["seated", "Seat"],
    ["no_show", "No-show"],
    ["cancelled", "Cancel"],
  ],
  seated: [["completed", "Complete"]],
  completed: [],
  no_show: [],
  cancelled: [],
};

const label = (status) => status.replace("_", " ");

function NewBooking({ day, onCreated }) {
  const [form, setForm] = useState({ guest_name: "", phone: "", party_size: "2", notes: "" });
  const [date, setDate] = useState(day);
  const [slots, setSlots] = useState([]);
  const [start, setStart] = useState("");
  const [error, setError] = useState(null);

  const partySize = Number(form.party_size);

  useEffect(() => {
    if (!date || !(partySize >= 1)) return undefined;
    const controller = new AbortController();
    request(`/api/bookings/availability?booking_date=${date}&party_size=${partySize}`, {
      signal: controller.signal,
    })
      .then((result) => {
        setSlots(result.slots);
        setStart((current) => (result.slots.some((s) => s.start_time === current && s.available) ? current : ""));
      })
      .catch((err) => {
        if (err.name !== "AbortError") setError(err.message);
      });
    return () => controller.abort();
  }, [date, partySize]);

  async function submit(event) {
    event.preventDefault();
    setError(null);
    try {
      await request("/api/bookings", {
        method: "POST",
        body: {
          guest_name: form.guest_name,
          phone: form.phone,
          party_size: partySize,
          booking_date: date,
          start_time: start,
          notes: form.notes || null,
        },
      });
      setForm({ guest_name: "", phone: "", party_size: form.party_size, notes: "" });
      setStart("");
      onCreated(date);
    } catch (err) {
      setError(err.message);
    }
  }

  const free = slots.filter((slot) => slot.available);

  return (
    <section className="card" aria-label="New booking">
      <h2>New booking</h2>
      <form className="stack" onSubmit={submit}>
        <label>
          Guest name
          <input
            value={form.guest_name}
            onChange={(e) => setForm({ ...form, guest_name: e.target.value })}
            required
          />
        </label>
        <label>
          Mobile number
          <input
            inputMode="tel"
            value={form.phone}
            onChange={(e) => setForm({ ...form, phone: e.target.value })}
            required
          />
        </label>
        <label>
          Guests
          <input
            type="number"
            min="1"
            value={form.party_size}
            onChange={(e) => setForm({ ...form, party_size: e.target.value })}
            required
          />
        </label>
        <label>
          Date
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
        </label>
        <label>
          Time
          <select value={start} onChange={(e) => setStart(e.target.value)} required>
            <option value="">{free.length ? "Choose a time" : "No free slots"}</option>
            {free.map((slot) => (
              <option key={slot.start_time} value={slot.start_time}>
                {clock(slot.start_time)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Notes
          <input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        </label>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button className="button" type="submit" disabled={!start}>
          Book table
        </button>
      </form>
    </section>
  );
}

export default function BookingsTab() {
  const [day, setDay] = useState(todayInput());
  const [bookings, setBookings] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      setBookings(await request(`/api/bookings?booking_date=${day}`));
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }, [day]);

  useEffect(() => {
    load();
  }, [load]);

  async function setStatus(booking, status) {
    setError(null);
    try {
      await request(`/api/bookings/${booking.id}/status`, { method: "POST", body: { status } });
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="orders-layout">
      <div>
        <label>
          Day
          <input type="date" value={day} onChange={(e) => setDay(e.target.value)} />
        </label>

        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}

        {bookings === null ? (
          <p className="muted">Loading...</p>
        ) : bookings.length === 0 ? (
          <p className="muted">No bookings for this day.</p>
        ) : (
          <ul className="list" aria-label="Bookings">
            {bookings.map((booking) => (
              <li key={booking.id} className="card booking">
                <div className="row space-between">
                  <strong>
                    {clock(booking.start_time)}–{clock(booking.end_time)} · {booking.guest_name}
                  </strong>
                  <span className={`badge badge-${booking.status}`}>{label(booking.status)}</span>
                </div>
                <p className="muted">
                  {booking.party_size} {booking.party_size === 1 ? "guest" : "guests"} · {booking.phone}
                  {booking.notes ? ` · ${booking.notes}` : ""}
                </p>
                <div className="row">
                  {NEXT[booking.status].map(([status, text]) => (
                    <button
                      key={status}
                      className={`button ${status === "cancelled" || status === "no_show" ? "secondary" : ""}`}
                      aria-label={`${text} ${booking.guest_name}`}
                      onClick={() => setStatus(booking, status)}
                    >
                      {text}
                    </button>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <NewBooking
        day={day}
        onCreated={(date) => {
          if (date === day) load();
          else setDay(date);
        }}
      />
    </div>
  );
}

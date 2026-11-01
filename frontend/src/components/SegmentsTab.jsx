import { useCallback, useEffect, useState } from "react";
import { formatMoney, request } from "../api.js";

export const SEGMENTS = [
  ["regular", "Regular"],
  ["new", "New"],
  ["at_risk", "At risk"],
  ["lost", "Lost"],
];

export const segmentName = (id) => SEGMENTS.find(([value]) => value === id)?.[1] ?? id;

function Thresholds() {
  const [form, setForm] = useState(null);
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    request("/api/retention/settings")
      .then(setForm)
      .catch((err) => setError(err.message));
  }, []);

  if (!form) return error ? <p className="error" role="alert">{error}</p> : null;

  const change = (field) => (e) => {
    setMessage(null);
    setForm({ ...form, [field]: e.target.value });
  };

  async function save(event) {
    event.preventDefault();
    setError(null);
    try {
      await request("/api/retention/settings", {
        method: "PUT",
        body: {
          at_risk_days: Number(form.at_risk_days),
          lost_days: Number(form.lost_days),
        },
      });
      setMessage("Thresholds saved.");
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section className="card" aria-label="Segment thresholds">
      <h2>Thresholds</h2>
      <form className="stack" onSubmit={save}>
        <label>
          At risk after (days without a visit)
          <input type="number" min="1" value={form.at_risk_days} onChange={change("at_risk_days")} required />
        </label>
        <label>
          Lost after (days without a visit)
          <input type="number" min="1" value={form.lost_days} onChange={change("lost_days")} required />
        </label>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {message && <p role="status">{message}</p>}
        <button className="button" type="submit">
          Save thresholds
        </button>
      </form>
    </section>
  );
}

export default function SegmentsTab() {
  const [filter, setFilter] = useState("");
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      setData(await request(`/api/retention/segments${filter ? `?segment=${filter}` : ""}`));
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="stack">
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!data && !error && <p className="muted">Loading...</p>}

      {data && (
        <>
          <div className="chips" role="group" aria-label="Segment filter">
            <button className={`chip ${filter === "" ? "active" : ""}`} onClick={() => setFilter("")}>
              All
            </button>
            {data.summary.map((entry) => (
              <button
                key={entry.segment}
                className={`chip ${filter === entry.segment ? "active" : ""}`}
                onClick={() => setFilter(entry.segment)}
              >
                {segmentName(entry.segment)} ({entry.customers})
              </button>
            ))}
          </div>

          <section className="card">
            <h2>Customers</h2>
            <p className="muted">
              Scores run 1 (low) to 5 (high) for recency, frequency and spend. Only guests who have
              been billed appear here.
            </p>
            {data.members.length === 0 ? (
              <p className="muted">No customers in this segment.</p>
            ) : (
              <div className="table-scroll">
                <table className="data-table" aria-label="Customer segments">
                  <thead>
                    <tr>
                      <th>Guest</th>
                      <th>Segment</th>
                      <th>Visits</th>
                      <th>Spent</th>
                      <th>Last visit</th>
                      <th>R</th>
                      <th>F</th>
                      <th>M</th>
                      <th>Marketing</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.members.map((member) => (
                      <tr key={member.customer_id}>
                        <td>
                          {member.name || "Guest"} <span className="muted">{member.phone}</span>
                        </td>
                        <td>{segmentName(member.segment)}</td>
                        <td>{member.visits}</td>
                        <td>{formatMoney(member.total_spent)}</td>
                        <td>{member.days_since_visit}d ago</td>
                        <td>{member.recency_score}</td>
                        <td>{member.frequency_score}</td>
                        <td>{member.monetary_score}</td>
                        <td>{member.marketing_opt_out ? "Opted out" : "OK"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}

      <Thresholds />
    </div>
  );
}

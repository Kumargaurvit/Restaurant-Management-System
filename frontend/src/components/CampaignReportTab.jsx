import { useEffect, useState } from "react";
import { request } from "../api.js";

export default function CampaignReportTab() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    request("/api/retention/report")
      .then(setRows)
      .catch((err) => setError(err.message));
  }, []);

  return (
    <section className="card">
      <h2>Campaign results</h2>
      <p className="muted">
        Replied counts guests who wrote back after the message. Returned counts guests billed again
        after it.
      </p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {rows === null && !error && <p className="muted">Loading...</p>}
      {rows && rows.length === 0 && <p className="muted">No campaigns yet.</p>}
      {rows && rows.length > 0 && (
        <div className="table-scroll">
          <table className="data-table" aria-label="Campaign results">
            <thead>
              <tr>
                <th>Rule</th>
                <th>Sent</th>
                <th>Waiting</th>
                <th>Rejected</th>
                <th>Failed</th>
                <th>Opted out</th>
                <th>Replied</th>
                <th>Returned</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.rule_id}>
                  <td>{row.rule_name}</td>
                  <td>{row.sent}</td>
                  <td>{row.pending}</td>
                  <td>{row.rejected}</td>
                  <td>{row.failed}</td>
                  <td>{row.skipped}</td>
                  <td>{row.replied}</td>
                  <td>{row.visited_after}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

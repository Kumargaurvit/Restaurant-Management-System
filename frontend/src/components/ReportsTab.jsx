import { useEffect, useState } from "react";
import { formatMoney, request } from "../api.js";

const todayInput = () => new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD

export default function ReportsTab() {
  const [day, setDay] = useState(todayInput());
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    request(`/api/billing/reports/daily?day=${day}`, { signal: controller.signal })
      .then(setReport)
      .catch((err) => {
        if (err.name !== "AbortError") setError(err.message);
      });
    return () => controller.abort();
  }, [day]);

  return (
    <section className="card">
      <h2>Daily sales</h2>
      <label>
        Day
        <input type="date" value={day} onChange={(e) => setDay(e.target.value)} />
      </label>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {report && (
        <dl className="report">
          <dt>Bills</dt>
          <dd>{report.bill_count}</dd>
          <dt className="total">Total sales</dt>
          <dd className="total">{formatMoney(report.total_sales)}</dd>
          <dt>Cash received</dt>
          <dd>{formatMoney(report.cash)}</dd>
          <dt>UPI received</dt>
          <dd>{formatMoney(report.upi)}</dd>
          <dt>Card received</dt>
          <dd>{formatMoney(report.card)}</dd>
        </dl>
      )}
    </section>
  );
}

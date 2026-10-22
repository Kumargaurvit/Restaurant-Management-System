import { useEffect, useState } from "react";
import { formatMoney, request } from "../api.js";

const PERIODS = [
  { value: "7", label: "Last 7 days" },
  { value: "30", label: "Last 30 days" },
  { value: "90", label: "Last 90 days" },
  { value: "", label: "All time" },
];

const formatDate = (value) => (value ? new Date(value).toLocaleDateString("en-IN") : "-");

export default function InsightsTab() {
  const [days, setDays] = useState("30");
  const [dishes, setDishes] = useState(null);
  const [customers, setCustomers] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    const query = days ? `?days=${days}&limit=10` : "?limit=10";
    setError(null);
    Promise.all([
      request(`/api/reports/top-dishes${query}`, { signal: controller.signal }),
      request(`/api/reports/top-customers${query}`, { signal: controller.signal }),
    ])
      .then(([topDishes, topCustomers]) => {
        setDishes(topDishes);
        setCustomers(topCustomers);
      })
      .catch((err) => {
        if (err.name !== "AbortError") setError(err.message);
      });
    return () => controller.abort();
  }, [days]);

  return (
    <div className="stack">
      <label>
        Period
        <select value={days} onChange={(e) => setDays(e.target.value)}>
          {PERIODS.map((period) => (
            <option key={period.value} value={period.value}>
              {period.label}
            </option>
          ))}
        </select>
      </label>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <section className="card">
        <h2>Most ordered dishes</h2>
        {dishes === null ? (
          <p className="muted">Loading...</p>
        ) : dishes.length === 0 ? (
          <p className="muted">No billed orders in this period yet.</p>
        ) : (
          <table className="data-table" aria-label="Most ordered dishes">
            <thead>
              <tr>
                <th>#</th>
                <th>Dish</th>
                <th className="num">Qty sold</th>
                <th className="num">Orders</th>
                <th className="num">Sales (before GST)</th>
              </tr>
            </thead>
            <tbody>
              {dishes.map((dish, index) => (
                <tr key={dish.menu_item_id}>
                  <td>{index + 1}</td>
                  <td>{dish.name}</td>
                  <td className="num">{dish.quantity}</td>
                  <td className="num">{dish.orders}</td>
                  <td className="num">{formatMoney(dish.revenue)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <h2>Most frequent customers</h2>
        {customers === null ? (
          <p className="muted">Loading...</p>
        ) : customers.length === 0 ? (
          <p className="muted">
            No customers yet. Add a guest's mobile number to an order to start tracking visits.
          </p>
        ) : (
          <table className="data-table" aria-label="Most frequent customers">
            <thead>
              <tr>
                <th>#</th>
                <th>Customer</th>
                <th className="num">Visits</th>
                <th className="num">Spent</th>
                <th>Last visit</th>
              </tr>
            </thead>
            <tbody>
              {customers.map((customer, index) => (
                <tr key={customer.id}>
                  <td>{index + 1}</td>
                  <td>
                    {customer.name || "Guest"} <span className="muted">{customer.phone}</span>
                    {customer.is_returning && <span className="badge badge-ok">Returning</span>}
                  </td>
                  <td className="num">{customer.visits}</td>
                  <td className="num">{formatMoney(customer.total_spent)}</td>
                  <td>{formatDate(customer.last_visit)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

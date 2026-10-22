import { useEffect, useState } from "react";
import { formatMoney, request } from "../api.js";

const formatDate = (value) => (value ? new Date(value).toLocaleDateString("en-IN") : "-");

export default function CustomersTab() {
  const [search, setSearch] = useState("");
  const [customers, setCustomers] = useState(null);
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    const query = search.trim() ? `?search=${encodeURIComponent(search.trim())}` : "";
    request(`/api/customers${query}`, { signal: controller.signal })
      .then((list) => {
        setCustomers(list);
        setError(null);
      })
      .catch((err) => {
        if (err.name !== "AbortError") setError(err.message);
      });
    return () => controller.abort();
  }, [search]);

  async function open(customerId) {
    setError(null);
    try {
      setDetail(await request(`/api/customers/${customerId}`));
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="orders-layout">
      <div>
        <label>
          Search by name or number
          <input value={search} onChange={(e) => setSearch(e.target.value)} />
        </label>

        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}

        {customers === null ? (
          <p className="muted">Loading...</p>
        ) : customers.length === 0 ? (
          <p className="muted">
            {search ? "No matching customers." : "No customers yet. Add a guest's number to an order."}
          </p>
        ) : (
          <ul className="list" aria-label="Customers">
            {customers.map((customer) => (
              <li key={customer.id}>
                <button className="list-button" onClick={() => open(customer.id)}>
                  <strong>{customer.name || "Guest"}</strong> <span className="muted">{customer.phone}</span>
                  <br />
                  <span className="muted">
                    {customer.visits} {customer.visits === 1 ? "visit" : "visits"} ·{" "}
                    {formatMoney(customer.total_spent)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {detail && (
        <section className="card" aria-label="Customer details">
          <div className="row space-between">
            <h2>{detail.name || "Guest"}</h2>
            <button className="button secondary" onClick={() => setDetail(null)}>
              Close
            </button>
          </div>
          <dl className="report">
            <dt>Mobile</dt>
            <dd>{detail.phone}</dd>
            <dt>Visits</dt>
            <dd>{detail.visits}</dd>
            <dt>Total spent</dt>
            <dd>{formatMoney(detail.total_spent)}</dd>
            <dt>First visit</dt>
            <dd>{formatDate(detail.first_visit)}</dd>
            <dt>Last visit</dt>
            <dd>{formatDate(detail.last_visit)}</dd>
          </dl>

          <h3>Favourite dishes</h3>
          {detail.favourite_dishes.length === 0 ? (
            <p className="muted">Nothing ordered yet.</p>
          ) : (
            <ul className="lines" aria-label="Favourite dishes">
              {detail.favourite_dishes.map((dish) => (
                <li key={dish.menu_item_id}>
                  <span className="line-name">{dish.name}</span>
                  <span>× {dish.quantity}</span>
                </li>
              ))}
            </ul>
          )}

          <h3>Order history</h3>
          {detail.orders.length === 0 ? (
            <p className="muted">No billed orders yet.</p>
          ) : (
            <ul className="lines" aria-label="Order history">
              {detail.orders.map((order) => (
                <li key={order.order_id} className="history-item">
                  <div>
                    <strong>{order.invoice_number}</strong>{" "}
                    <span className="muted">
                      {formatDate(order.billed_at)} · {order.order_type.replace("_", " ")} ·{" "}
                      {order.bill_status}
                    </span>
                    <br />
                    <span className="muted">
                      {order.items.map((item) => `${item.quantity} × ${item.name}`).join(", ")}
                    </span>
                  </div>
                  <span className="line-amount">{formatMoney(order.total)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}

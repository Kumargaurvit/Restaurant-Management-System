import { useCallback, useEffect, useState } from "react";
import { formatMoney, request } from "../api.js";
import OrderPanel from "./OrderPanel.jsx";

export default function OrdersTab({ tables, menuItems, categories }) {
  const [openOrders, setOpenOrders] = useState([]);
  const [unpaidBills, setUnpaidBills] = useState([]);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState(null);
  const [delivery, setDelivery] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const [orders, bills] = await Promise.all([
        request("/api/billing/orders?status=open"),
        request("/api/billing/bills?status=unpaid"),
      ]);
      setOpenOrders(orders);
      setUnpaidBills(bills);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function createOrder(body) {
    setError(null);
    try {
      const order = await request("/api/billing/orders", { method: "POST", body });
      setSelected(order);
      setDelivery(null);
      refresh();
    } catch (err) {
      setError(err.message);
    }
  }

  async function openOrder(orderId) {
    setError(null);
    try {
      setSelected(await request(`/api/billing/orders/${orderId}`));
    } catch (err) {
      setError(err.message);
    }
  }

  function updateSelected(order) {
    setSelected(order);
    refresh();
  }

  function submitDelivery(event) {
    event.preventDefault();
    createOrder({
      order_type: "delivery",
      customer_name: delivery.name || null,
      customer_phone: delivery.phone || null,
      delivery_address: delivery.address,
    });
  }

  const orderByTable = new Map(openOrders.filter((o) => o.table_id).map((o) => [o.table_id, o]));
  const activeTables = tables.filter((table) => table.is_active);

  return (
    <div className="orders-layout">
      <div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}

        <h2>Tables</h2>
        {activeTables.length === 0 ? (
          <p className="muted">No tables yet. Add tables in the Menu tab.</p>
        ) : (
          <div className="table-grid">
            {activeTables.map((table) => {
              const existing = orderByTable.get(table.id);
              return (
                <button
                  key={table.id}
                  className={`table-button ${existing ? "occupied" : ""}`}
                  onClick={() =>
                    existing
                      ? openOrder(existing.id)
                      : createOrder({ order_type: "dine_in", table_id: table.id })
                  }
                  aria-label={`${table.name} ${existing ? "occupied" : "free"}`}
                >
                  <strong>{table.name}</strong>
                  <span className="muted">{existing ? "Occupied" : `Free · ${table.capacity} seats`}</span>
                </button>
              );
            })}
          </div>
        )}

        <div className="row">
          <button className="button secondary" onClick={() => createOrder({ order_type: "takeaway" })}>
            New takeaway
          </button>
          <button
            className="button secondary"
            onClick={() => setDelivery({ name: "", phone: "", address: "" })}
          >
            New delivery
          </button>
        </div>

        {delivery && (
          <form className="card" onSubmit={submitDelivery} aria-label="New delivery order">
            <label>
              Customer name
              <input
                value={delivery.name}
                onChange={(e) => setDelivery({ ...delivery, name: e.target.value })}
              />
            </label>
            <label>
              Phone
              <input
                value={delivery.phone}
                onChange={(e) => setDelivery({ ...delivery, phone: e.target.value })}
              />
            </label>
            <label>
              Delivery address
              <input
                value={delivery.address}
                onChange={(e) => setDelivery({ ...delivery, address: e.target.value })}
                required
              />
            </label>
            <div className="row">
              <button className="button" type="submit">
                Start order
              </button>
              <button className="button secondary" type="button" onClick={() => setDelivery(null)}>
                Cancel
              </button>
            </div>
          </form>
        )}

        <h2>Open orders</h2>
        {openOrders.length === 0 ? (
          <p className="muted">No open orders.</p>
        ) : (
          <ul className="list">
            {openOrders.map((order) => (
              <li key={order.id}>
                <button className="list-button" onClick={() => openOrder(order.id)}>
                  Order #{order.id} · {order.order_type.replace("_", " ")} · {order.items.length} items
                </button>
              </li>
            ))}
          </ul>
        )}

        <h2>Awaiting payment</h2>
        {unpaidBills.length === 0 ? (
          <p className="muted">Nothing to collect.</p>
        ) : (
          <ul className="list">
            {unpaidBills.map((bill) => (
              <li key={bill.id}>
                <button className="list-button" onClick={() => openOrder(bill.order_id)}>
                  {bill.invoice_number} · due {formatMoney(bill.amount_due)}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {selected && (
        <OrderPanel
          key={selected.id}
          order={selected}
          menuItems={menuItems}
          categories={categories}
          onOrderChange={updateSelected}
          onBillChange={refresh}
          onClose={() => {
            setSelected(null);
            refresh();
          }}
        />
      )}
    </div>
  );
}

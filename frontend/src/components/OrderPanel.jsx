import { useEffect, useMemo, useState } from "react";
import { formatMoney, request } from "../api.js";
import { canBill, useAuth } from "../auth.jsx";
import CustomerBox from "./CustomerBox.jsx";
import PrintPreview from "./PrintPreview.jsx";

const PAYMENT_MODES = ["cash", "upi", "card"];

export default function OrderPanel({ order, menuItems, categories, onOrderChange, onBillChange, onClose }) {
  const { user } = useAuth();
  const [bill, setBill] = useState(null);
  const [categoryId, setCategoryId] = useState("all");
  const [discount, setDiscount] = useState("");
  const [mode, setMode] = useState("cash");
  const [amount, setAmount] = useState("");
  const [reference, setReference] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(null);

  const isOpen = order.status === "open";

  // A billed order: load its bill so payment can continue (e.g. after a page reload).
  useEffect(() => {
    setBill(null);
    setError(null);
    if (order.status !== "billed") return undefined;
    const controller = new AbortController();
    request(`/api/billing/orders/${order.id}/bill`, { signal: controller.signal })
      .then(setBill)
      .catch((err) => {
        if (err.name !== "AbortError") setError(err.message);
      });
    return () => controller.abort();
  }, [order.id, order.status]);

  useEffect(() => {
    if (bill) setAmount(bill.status === "paid" ? "" : String(Number(bill.amount_due).toFixed(2)));
  }, [bill]);

  const visibleItems = useMemo(
    () =>
      menuItems.filter(
        (item) =>
          item.is_available && (categoryId === "all" || item.category_id === Number(categoryId)),
      ),
    [menuItems, categoryId],
  );

  const estimate = useMemo(
    () => order.items.reduce((sum, line) => sum + Number(line.unit_price) * line.quantity, 0),
    [order.items],
  );
  const hasUnsent = order.items.some((line) => line.kitchen_ticket_id === null);

  async function run(action) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const addItem = (menuItemId) =>
    run(async () => {
      const updated = await request(`/api/billing/orders/${order.id}/items`, {
        method: "POST",
        body: { menu_item_id: menuItemId, quantity: 1 },
      });
      onOrderChange(updated);
    });

  const setQuantity = (line, quantity) =>
    run(async () => {
      const updated = await request(`/api/billing/orders/${order.id}/items/${line.id}`, {
        method: "PATCH",
        body: { quantity },
      });
      onOrderChange(updated);
    });

  const sendToKitchen = () =>
    run(async () => {
      const ticket = await request(`/api/billing/orders/${order.id}/kot`, { method: "POST" });
      const text = await request(`/api/billing/kot/${ticket.id}/print`, { as: "text" });
      onOrderChange(await request(`/api/billing/orders/${order.id}`));
      setPreview({ title: `Kitchen ticket #${ticket.id}`, text });
    });

  const generateBill = () =>
    run(async () => {
      const created = await request(`/api/billing/orders/${order.id}/bill`, {
        method: "POST",
        body: { discount: discount === "" ? "0" : discount },
      });
      setBill(created);
      onOrderChange(await request(`/api/billing/orders/${order.id}`));
      onBillChange();
    });

  const cancelOrder = () =>
    run(async () => {
      await request(`/api/billing/orders/${order.id}/cancel`, { method: "POST" });
      onClose(true);
    });

  const takePayment = (event) => {
    event.preventDefault();
    return run(async () => {
      const updated = await request(`/api/billing/bills/${bill.id}/payments`, {
        method: "POST",
        body: { mode, amount, reference: reference || null },
      });
      setBill(updated);
      setReference("");
      onBillChange();
    });
  };

  const showReceipt = () =>
    run(async () => {
      const text = await request(`/api/billing/bills/${bill.id}/receipt`, { as: "text" });
      setPreview({ title: `Receipt ${bill.invoice_number}`, text });
    });

  const heading =
    order.order_type === "dine_in"
      ? `Table order #${order.id}`
      : `${order.order_type === "takeaway" ? "Takeaway" : "Delivery"} order #${order.id}`;

  return (
    <section className="order-panel card" aria-label="Current order">
      <div className="row space-between">
        <h2>{heading}</h2>
        <button className="button secondary" onClick={() => onClose(false)}>
          Close
        </button>
      </div>
      {order.delivery_address && <p className="muted">{order.delivery_address}</p>}
      <CustomerBox order={order} onOrderChange={onOrderChange} />

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {isOpen && (
        <>
          <div className="chips" role="tablist" aria-label="Menu categories">
            <button
              className={`chip ${categoryId === "all" ? "active" : ""}`}
              onClick={() => setCategoryId("all")}
            >
              All
            </button>
            {categories.map((category) => (
              <button
                key={category.id}
                className={`chip ${String(category.id) === String(categoryId) ? "active" : ""}`}
                onClick={() => setCategoryId(category.id)}
              >
                {category.name}
              </button>
            ))}
          </div>

          {visibleItems.length === 0 ? (
            <p className="muted">No menu items yet. Add some in the Menu tab.</p>
          ) : (
            <div className="item-grid">
              {visibleItems.map((item) => (
                <button
                  key={item.id}
                  className="item-button"
                  disabled={busy}
                  onClick={() => addItem(item.id)}
                  aria-label={`Add ${item.name}`}
                >
                  <strong>{item.name}</strong>
                  <span className="muted">{formatMoney(item.price)}</span>
                </button>
              ))}
            </div>
          )}
        </>
      )}

      <h3>Items</h3>
      {order.items.length === 0 ? (
        <p className="muted">Tap a menu item to add it.</p>
      ) : (
        <ul className="lines" aria-label="Order items">
          {order.items.map((line) => (
            <li key={line.id}>
              <span className="line-name">
                {line.name}
                {line.kitchen_ticket_id !== null && <span className="badge badge-ok">sent</span>}
              </span>
              {isOpen ? (
                <span className="stepper">
                  <button
                    className="icon-button"
                    aria-label={`Decrease ${line.name}`}
                    disabled={busy}
                    onClick={() => setQuantity(line, line.quantity - 1)}
                  >
                    −
                  </button>
                  <span aria-label={`${line.name} quantity`}>{line.quantity}</span>
                  <button
                    className="icon-button"
                    aria-label={`Increase ${line.name}`}
                    disabled={busy}
                    onClick={() => setQuantity(line, line.quantity + 1)}
                  >
                    +
                  </button>
                </span>
              ) : (
                <span>× {line.quantity}</span>
              )}
              <span className="line-amount">{formatMoney(Number(line.unit_price) * line.quantity)}</span>
            </li>
          ))}
        </ul>
      )}

      {isOpen && (
        <>
          <p className="muted">Subtotal before GST: {formatMoney(estimate)}</p>
          <div className="row">
            <button className="button secondary" disabled={busy || !hasUnsent} onClick={sendToKitchen}>
              Send to kitchen
            </button>
            {user?.role !== "waiter" && order.items.length === 0 && (
              <button className="button secondary" disabled={busy} onClick={cancelOrder}>
                Cancel order
              </button>
            )}
          </div>

          {canBill(user) && (
            <div className="row bill-row">
              <label>
                Discount (₹)
                <input
                  inputMode="decimal"
                  value={discount}
                  onChange={(e) => setDiscount(e.target.value)}
                  placeholder="0"
                />
              </label>
              <button
                className="button"
                disabled={busy || order.items.length === 0}
                onClick={generateBill}
              >
                Generate bill
              </button>
            </div>
          )}
        </>
      )}

      {bill && (
        <div className="bill" aria-label="Bill">
          <h3>Bill {bill.invoice_number}</h3>
          <dl>
            <dt>Subtotal</dt>
            <dd>{formatMoney(bill.subtotal)}</dd>
            {Number(bill.discount) > 0 && (
              <>
                <dt>Discount</dt>
                <dd>−{formatMoney(bill.discount)}</dd>
              </>
            )}
            <dt>CGST</dt>
            <dd>{formatMoney(bill.cgst)}</dd>
            <dt>SGST</dt>
            <dd>{formatMoney(bill.sgst)}</dd>
            {Number(bill.round_off) !== 0 && (
              <>
                <dt>Round off</dt>
                <dd>{formatMoney(bill.round_off)}</dd>
              </>
            )}
            <dt className="total">Total</dt>
            <dd className="total">{formatMoney(bill.total)}</dd>
            <dt>Paid</dt>
            <dd>{formatMoney(bill.amount_paid)}</dd>
            <dt>Due</dt>
            <dd>{formatMoney(bill.amount_due)}</dd>
          </dl>

          {bill.status === "paid" ? (
            <p>
              <span className="badge badge-ok">Paid</span>
            </p>
          ) : (
            canBill(user) && (
              <form className="row payment-form" onSubmit={takePayment}>
                <label>
                  Mode
                  <select value={mode} onChange={(e) => setMode(e.target.value)}>
                    {PAYMENT_MODES.map((option) => (
                      <option key={option} value={option}>
                        {option.toUpperCase()}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Amount (₹)
                  <input
                    inputMode="decimal"
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    required
                  />
                </label>
                {mode !== "cash" && (
                  <label>
                    Reference
                    <input value={reference} onChange={(e) => setReference(e.target.value)} />
                  </label>
                )}
                <button className="button" type="submit" disabled={busy}>
                  Take payment
                </button>
              </form>
            )
          )}
          <button className="button secondary" disabled={busy} onClick={showReceipt}>
            Print receipt
          </button>
        </div>
      )}

      {preview && (
        <PrintPreview title={preview.title} text={preview.text} onClose={() => setPreview(null)} />
      )}
    </section>
  );
}

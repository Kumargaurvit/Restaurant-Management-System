import { useState } from "react";
import { formatMoney, request } from "../api.js";

export default function MenuTab({ categories, menuItems, tables, reload }) {
  const [error, setError] = useState(null);
  const [categoryName, setCategoryName] = useState("");
  const [item, setItem] = useState({ category_id: "", name: "", price: "", gst_rate: "5" });
  const [table, setTable] = useState({ name: "", capacity: "4" });

  async function submit(path, body, reset) {
    setError(null);
    try {
      await request(path, { method: "POST", body });
      reset();
      await reload();
    } catch (err) {
      setError(err.message);
    }
  }

  async function toggleAvailability(menuItem) {
    setError(null);
    try {
      await request(`/api/billing/menu/items/${menuItem.id}`, {
        method: "PATCH",
        body: { is_available: !menuItem.is_available },
      });
      await reload();
    } catch (err) {
      setError(err.message);
    }
  }

  const categoryName_ = (id) => categories.find((category) => category.id === id)?.name ?? "";

  return (
    <div className="menu-layout">
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <section className="card">
        <h2>Categories</h2>
        <form
          className="row"
          onSubmit={(e) => {
            e.preventDefault();
            submit("/api/billing/menu/categories", { name: categoryName }, () => setCategoryName(""));
          }}
        >
          <label>
            New category
            <input value={categoryName} onChange={(e) => setCategoryName(e.target.value)} required />
          </label>
          <button className="button" type="submit">
            Add category
          </button>
        </form>
        <p className="muted">{categories.map((category) => category.name).join(" · ") || "None yet."}</p>
      </section>

      <section className="card">
        <h2>Add menu item</h2>
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault();
            submit(
              "/api/billing/menu/items",
              { ...item, category_id: Number(item.category_id) },
              () => setItem({ ...item, name: "", price: "" }),
            );
          }}
        >
          <label>
            Category
            <select
              value={item.category_id}
              onChange={(e) => setItem({ ...item, category_id: e.target.value })}
              required
            >
              <option value="">Select...</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Item name
            <input value={item.name} onChange={(e) => setItem({ ...item, name: e.target.value })} required />
          </label>
          <label>
            Price (₹, excluding GST)
            <input
              inputMode="decimal"
              value={item.price}
              onChange={(e) => setItem({ ...item, price: e.target.value })}
              required
            />
          </label>
          <label>
            GST rate
            <select value={item.gst_rate} onChange={(e) => setItem({ ...item, gst_rate: e.target.value })}>
              {["0", "5", "12", "18", "28"].map((rate) => (
                <option key={rate} value={rate}>
                  {rate}%
                </option>
              ))}
            </select>
          </label>
          <button className="button" type="submit">
            Add item
          </button>
        </form>
      </section>

      <section className="card">
        <h2>Menu</h2>
        {menuItems.length === 0 ? (
          <p className="muted">No items yet.</p>
        ) : (
          <ul className="lines">
            {menuItems.map((menuItem) => (
              <li key={menuItem.id}>
                <span className="line-name">
                  {menuItem.name} <span className="muted">{categoryName_(menuItem.category_id)}</span>
                </span>
                <span>
                  {formatMoney(menuItem.price)} · {Number(menuItem.gst_rate)}%
                </span>
                <button className="button secondary" onClick={() => toggleAvailability(menuItem)}>
                  {menuItem.is_available ? "Mark unavailable" : "Mark available"}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card">
        <h2>Tables</h2>
        <form
          className="row"
          onSubmit={(e) => {
            e.preventDefault();
            submit(
              "/api/billing/tables",
              { name: table.name, capacity: Number(table.capacity) },
              () => setTable({ name: "", capacity: "4" }),
            );
          }}
        >
          <label>
            Table name
            <input value={table.name} onChange={(e) => setTable({ ...table, name: e.target.value })} required />
          </label>
          <label>
            Seats
            <input
              type="number"
              min="1"
              value={table.capacity}
              onChange={(e) => setTable({ ...table, capacity: e.target.value })}
              required
            />
          </label>
          <button className="button" type="submit">
            Add table
          </button>
        </form>
        <p className="muted">
          {tables.map((entry) => `${entry.name} (${entry.capacity})`).join(" · ") || "None yet."}
        </p>
      </section>
    </div>
  );
}

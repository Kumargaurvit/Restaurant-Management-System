import { useState } from "react";
import { formatMoney, request } from "../api.js";

const GST_RATES = ["0", "5", "12", "18", "28"];

// Delete needs a second click so a stray tap cannot remove something.
function DeleteButton({ label, onDelete }) {
  const [confirming, setConfirming] = useState(false);
  if (!confirming) {
    return (
      <button className="button secondary" onClick={() => setConfirming(true)}>
        {`Delete ${label}`}
      </button>
    );
  }
  return (
    <>
      <button className="button danger" onClick={onDelete}>
        {`Confirm delete ${label}`}
      </button>
      <button className="button secondary" onClick={() => setConfirming(false)}>
        Keep
      </button>
    </>
  );
}

function CategoryRow({ category, act, reload }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(category.name);

  if (editing) {
    return (
      <li>
        <form
          className="row"
          onSubmit={(e) => {
            e.preventDefault();
            act(async () => {
              await request(`/api/billing/menu/categories/${category.id}`, {
                method: "PATCH",
                body: { name },
              });
              setEditing(false);
              await reload();
            });
          }}
        >
          <label>
            {`Category name ${category.name}`}
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <button className="button" type="submit">
            Save category
          </button>
          <button className="button secondary" type="button" onClick={() => setEditing(false)}>
            Cancel
          </button>
        </form>
      </li>
    );
  }

  return (
    <li>
      <span className="line-name">{category.name}</span>
      <button className="button secondary" onClick={() => setEditing(true)}>
        {`Rename ${category.name}`}
      </button>
      <DeleteButton
        label={category.name}
        onDelete={() =>
          act(async () => {
            await request(`/api/billing/menu/categories/${category.id}`, { method: "DELETE" });
            await reload();
          })
        }
      />
    </li>
  );
}

function ItemRow({ item, categories, act, reload }) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({
    name: item.name,
    price: String(Number(item.price)),
    gst_rate: String(Number(item.gst_rate)),
    category_id: String(item.category_id),
  });
  const categoryName = categories.find((c) => c.id === item.category_id)?.name ?? "";

  if (editing) {
    return (
      <li>
        <form
          className="stack item-edit"
          onSubmit={(e) => {
            e.preventDefault();
            act(async () => {
              await request(`/api/billing/menu/items/${item.id}`, {
                method: "PATCH",
                body: { ...form, category_id: Number(form.category_id) },
              });
              setEditing(false);
              await reload();
            });
          }}
        >
          <label>
            {`Name of ${item.name}`}
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          </label>
          <label>
            {`Price of ${item.name}`}
            <input
              inputMode="decimal"
              value={form.price}
              onChange={(e) => setForm({ ...form, price: e.target.value })}
              required
            />
          </label>
          <label>
            {`GST of ${item.name}`}
            <select value={form.gst_rate} onChange={(e) => setForm({ ...form, gst_rate: e.target.value })}>
              {GST_RATES.map((rate) => (
                <option key={rate} value={rate}>
                  {rate}%
                </option>
              ))}
            </select>
          </label>
          <label>
            {`Category of ${item.name}`}
            <select
              value={form.category_id}
              onChange={(e) => setForm({ ...form, category_id: e.target.value })}
            >
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
          </label>
          <div className="row">
            <button className="button" type="submit">
              Save item
            </button>
            <button className="button secondary" type="button" onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
        </form>
      </li>
    );
  }

  return (
    <li>
      <span className="line-name">
        {item.name} <span className="muted">{categoryName}</span>
        {!item.is_available && <span className="badge badge-error">Unavailable</span>}
      </span>
      <span>
        {formatMoney(item.price)} · {Number(item.gst_rate)}%
      </span>
      <button className="button secondary" onClick={() => setEditing(true)}>
        {`Edit ${item.name}`}
      </button>
      <button
        className="button secondary"
        onClick={() =>
          act(async () => {
            await request(`/api/billing/menu/items/${item.id}`, {
              method: "PATCH",
              body: { is_available: !item.is_available },
            });
            await reload();
          })
        }
      >
        {item.is_available ? "Mark unavailable" : "Mark available"}
      </button>
      <DeleteButton
        label={item.name}
        onDelete={() =>
          act(async () => {
            await request(`/api/billing/menu/items/${item.id}`, { method: "DELETE" });
            await reload();
          })
        }
      />
    </li>
  );
}

function TableRow({ table, act, reload }) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({ name: table.name, capacity: String(table.capacity) });

  if (editing) {
    return (
      <li>
        <form
          className="row"
          onSubmit={(e) => {
            e.preventDefault();
            act(async () => {
              await request(`/api/billing/tables/${table.id}`, {
                method: "PATCH",
                body: { name: form.name, capacity: Number(form.capacity) },
              });
              setEditing(false);
              await reload();
            });
          }}
        >
          <label>
            {`Name of table ${table.name}`}
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          </label>
          <label>
            {`Seats at table ${table.name}`}
            <input
              type="number"
              min="1"
              value={form.capacity}
              onChange={(e) => setForm({ ...form, capacity: e.target.value })}
              required
            />
          </label>
          <button className="button" type="submit">
            Save table
          </button>
          <button className="button secondary" type="button" onClick={() => setEditing(false)}>
            Cancel
          </button>
        </form>
      </li>
    );
  }

  return (
    <li>
      <span className="line-name">
        {table.name} <span className="muted">{table.capacity} seats</span>
        {!table.is_active && <span className="badge badge-error">Inactive</span>}
      </span>
      <button className="button secondary" onClick={() => setEditing(true)}>
        {`Edit table ${table.name}`}
      </button>
      <button
        className="button secondary"
        onClick={() =>
          act(async () => {
            await request(`/api/billing/tables/${table.id}`, {
              method: "PATCH",
              body: { is_active: !table.is_active },
            });
            await reload();
          })
        }
      >
        {table.is_active ? `Deactivate ${table.name}` : `Activate ${table.name}`}
      </button>
      <DeleteButton
        label={`table ${table.name}`}
        onDelete={() =>
          act(async () => {
            await request(`/api/billing/tables/${table.id}`, { method: "DELETE" });
            await reload();
          })
        }
      />
    </li>
  );
}

export default function MenuTab({ categories, menuItems, tables, reload }) {
  const [error, setError] = useState(null);
  const [categoryName, setCategoryName] = useState("");
  const [item, setItem] = useState({ category_id: "", name: "", price: "", gst_rate: "5" });
  const [table, setTable] = useState({ name: "", capacity: "4" });

  // Runs an action, shows the server's message if it fails.
  async function act(action) {
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err.message);
    }
  }

  const submit = (path, body, reset) =>
    act(async () => {
      await request(path, { method: "POST", body });
      reset();
      await reload();
    });

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
        {categories.length === 0 ? (
          <p className="muted">None yet.</p>
        ) : (
          <ul className="lines" aria-label="Categories">
            {categories.map((category) => (
              <CategoryRow key={category.id} category={category} act={act} reload={reload} />
            ))}
          </ul>
        )}
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
              {GST_RATES.map((rate) => (
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
          <ul className="lines" aria-label="Menu items">
            {menuItems.map((menuItem) => (
              <ItemRow
                key={menuItem.id}
                item={menuItem}
                categories={categories}
                act={act}
                reload={reload}
              />
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
        {tables.length === 0 ? (
          <p className="muted">None yet.</p>
        ) : (
          <ul className="lines" aria-label="Tables">
            {tables.map((entry) => (
              <TableRow key={entry.id} table={entry} act={act} reload={reload} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

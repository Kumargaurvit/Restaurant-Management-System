import { useCallback, useEffect, useState } from "react";
import { request } from "../api.js";
import { canManage, useAuth } from "../auth.jsx";
import CustomersTab from "../components/CustomersTab.jsx";
import InsightsTab from "../components/InsightsTab.jsx";
import MenuTab from "../components/MenuTab.jsx";
import OrdersTab from "../components/OrdersTab.jsx";
import ReportsTab from "../components/ReportsTab.jsx";

export default function Billing() {
  const { user } = useAuth();
  const [tab, setTab] = useState("orders");
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      const [categories, menuItems, tables] = await Promise.all([
        request("/api/billing/menu/categories"),
        request("/api/billing/menu/items"),
        request("/api/billing/tables"),
      ]);
      setData({ categories, menuItems, tables });
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const tabs = [
    { id: "orders", label: "Orders" },
    ...(canManage(user)
      ? [
          { id: "menu", label: "Menu & tables" },
          { id: "customers", label: "Customers" },
          { id: "insights", label: "Insights" },
          { id: "reports", label: "Reports" },
        ]
      : []),
  ];

  return (
    <section>
      <h1>Billing</h1>
      <div className="tabs" role="tablist">
        {tabs.map((entry) => (
          <button
            key={entry.id}
            role="tab"
            aria-selected={tab === entry.id}
            className={`tab ${tab === entry.id ? "active" : ""}`}
            onClick={() => setTab(entry.id)}
          >
            {entry.label}
          </button>
        ))}
      </div>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!data && !error && <p className="muted">Loading...</p>}

      {data && tab === "orders" && <OrdersTab {...data} />}
      {data && tab === "menu" && <MenuTab {...data} reload={load} />}
      {tab === "customers" && <CustomersTab />}
      {tab === "insights" && <InsightsTab />}
      {tab === "reports" && <ReportsTab />}
    </section>
  );
}

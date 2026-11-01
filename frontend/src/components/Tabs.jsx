export default function Tabs({ tabs, active, onChange }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((entry) => (
        <button
          key={entry.id}
          role="tab"
          aria-selected={active === entry.id}
          className={`tab ${active === entry.id ? "active" : ""}`}
          onClick={() => onChange(entry.id)}
        >
          {entry.label}
        </button>
      ))}
    </div>
  );
}

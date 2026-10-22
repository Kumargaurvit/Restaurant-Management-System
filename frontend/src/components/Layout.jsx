import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth.jsx";
import { MODULES } from "../modules.js";

export default function Layout() {
  const [menuOpen, setMenuOpen] = useState(false);
  const { user, logout } = useAuth();

  return (
    <div className="app">
      <header className="topbar">
        <button
          className="icon-button"
          aria-label="Toggle navigation"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((open) => !open)}
        >
          ☰
        </button>
        <span className="brand">Restaurant Manager</span>
        <span className="spacer" />
        <span className="muted user-name">
          {user.name} · {user.role}
        </span>
        <button className="button secondary" onClick={logout}>
          Sign out
        </button>
      </header>

      <nav className={`sidebar ${menuOpen ? "open" : ""}`} onClick={() => setMenuOpen(false)}>
        <NavLink to="/" end className="nav-link">
          Dashboard
        </NavLink>
        {MODULES.map((module) => (
          <NavLink key={module.path} to={`/${module.path}`} className="nav-link">
            {module.name}
          </NavLink>
        ))}
        <NavLink to="/settings" className="nav-link">
          Settings
        </NavLink>
      </nav>

      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}

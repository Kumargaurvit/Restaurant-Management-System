import { useCallback, useEffect, useState } from "react";
import { request } from "../api.js";
import { useAuth } from "../auth.jsx";

const ROLES = ["owner", "manager", "cashier", "waiter"];
const NEW_STAFF = { name: "", email: "", password: "", role: "waiter" };

export default function StaffSection() {
  const { user } = useAuth();
  const [staff, setStaff] = useState(null);
  const [form, setForm] = useState(NEW_STAFF);
  const [resetFor, setResetFor] = useState(null);
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState(null);
  const [message, setMessage] = useState(null);

  const load = useCallback(async () => {
    try {
      setStaff(await request("/api/auth/users"));
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function attempt(action, success) {
    setError(null);
    setMessage(null);
    try {
      await action();
      if (success) setMessage(success);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  const update = (member, changes) =>
    attempt(() => request(`/api/auth/users/${member.id}`, { method: "PATCH", body: changes }));

  const addStaff = (event) => {
    event.preventDefault();
    return attempt(async () => {
      await request("/api/auth/users", { method: "POST", body: form });
      setForm(NEW_STAFF);
    }, "Staff member added.");
  };

  const resetPassword = (event) => {
    event.preventDefault();
    return attempt(async () => {
      await request(`/api/auth/users/${resetFor.id}/password`, {
        method: "POST",
        body: { password: newPassword },
      });
      setResetFor(null);
      setNewPassword("");
    }, "Password changed.");
  };

  return (
    <section className="card stack" aria-label="Staff">
      <h2>Staff</h2>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {message && <p role="status">{message}</p>}

      {staff === null ? (
        <p className="muted">Loading...</p>
      ) : (
        <ul className="lines" aria-label="Staff members">
          {staff.map((member) => (
            <li key={member.id} className="staff-row">
              <span className="line-name">
                <strong>{member.name}</strong>
                {member.id === user.id && <span className="muted"> (you)</span>}
                <br />
                <span className="muted">{member.email}</span>
                {!member.is_active && <span className="badge badge-error">Inactive</span>}
              </span>
              <select
                aria-label={`Role for ${member.name}`}
                value={member.role}
                onChange={(e) => update(member, { role: e.target.value })}
              >
                {ROLES.map((role) => (
                  <option key={role} value={role}>
                    {role}
                  </option>
                ))}
              </select>
              <button
                className="button secondary"
                onClick={() => update(member, { is_active: !member.is_active })}
              >
                {member.is_active ? "Deactivate" : "Reactivate"}
              </button>
              <button
                className="button secondary"
                onClick={() => {
                  setResetFor(member);
                  setNewPassword("");
                }}
              >
                Reset password
              </button>
            </li>
          ))}
        </ul>
      )}

      {resetFor && (
        <form className="row" onSubmit={resetPassword} aria-label="Reset password">
          <label>
            New password for {resetFor.name}
            <input
              type="password"
              minLength={8}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
            />
          </label>
          <button className="button" type="submit">
            Change password
          </button>
          <button className="button secondary" type="button" onClick={() => setResetFor(null)}>
            Cancel
          </button>
        </form>
      )}

      <h3>Add staff</h3>
      <form className="stack" onSubmit={addStaff} aria-label="Add staff">
        <label>
          Name
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
        </label>
        <label>
          Email
          <input
            type="email"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            required
          />
        </label>
        <label>
          Password (at least 8 characters)
          <input
            type="password"
            minLength={8}
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            required
          />
        </label>
        <label>
          Role
          <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            {ROLES.map((role) => (
              <option key={role} value={role}>
                {role}
              </option>
            ))}
          </select>
        </label>
        <div>
          <button className="button" type="submit">
            Add staff member
          </button>
        </div>
      </form>
    </section>
  );
}

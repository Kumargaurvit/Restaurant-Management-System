import { useCallback, useEffect, useState } from "react";
import { request } from "../api.js";
import { SEGMENTS, segmentName } from "./SegmentsTab.jsx";

const EMPTY = {
  name: "",
  segment: "at_risk",
  template: "Hi {name}, we miss you at {restaurant}! Come back this week and say hello.",
  mode: "approval",
  cooldown_days: "30",
};

export default function RulesTab() {
  const [rules, setRules] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [editing, setEditing] = useState(null);
  const [error, setError] = useState(null);
  const [runResult, setRunResult] = useState(null);

  const load = useCallback(async () => {
    try {
      setRules(await request("/api/retention/rules"));
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const change = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  async function save(event) {
    event.preventDefault();
    setError(null);
    const body = { ...form, cooldown_days: Number(form.cooldown_days), is_active: true };
    try {
      if (editing) {
        await request(`/api/retention/rules/${editing}`, { method: "PUT", body });
      } else {
        await request("/api/retention/rules", { method: "POST", body });
      }
      setForm(EMPTY);
      setEditing(null);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function toggle(rule) {
    setError(null);
    try {
      await request(`/api/retention/rules/${rule.id}`, {
        method: "PUT",
        body: {
          name: rule.name,
          segment: rule.segment,
          template: rule.template,
          mode: rule.mode,
          cooldown_days: rule.cooldown_days,
          is_active: !rule.is_active,
        },
      });
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  function edit(rule) {
    setEditing(rule.id);
    setForm({
      name: rule.name,
      segment: rule.segment,
      template: rule.template,
      mode: rule.mode,
      cooldown_days: String(rule.cooldown_days),
    });
  }

  async function runNow() {
    setError(null);
    try {
      setRunResult(await request("/api/retention/run", { method: "POST" }));
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="orders-layout">
      <div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}

        <div className="row space-between">
          <h2>Campaign rules</h2>
          <button className="button secondary" onClick={runNow}>
            Run rules now
          </button>
        </div>
        {runResult && (
          <p role="status">
            Ran {runResult.rules_run} rule(s): {runResult.queued} waiting for approval, {runResult.sent}{" "}
            sent, {runResult.skipped_cooldown} skipped (messaged recently).
          </p>
        )}

        {rules === null ? (
          <p className="muted">Loading...</p>
        ) : rules.length === 0 ? (
          <p className="muted">No rules yet. Add one to start winning guests back.</p>
        ) : (
          <ul className="list" aria-label="Campaign rules">
            {rules.map((rule) => (
              <li key={rule.id} className="card">
                <div className="row space-between">
                  <strong>{rule.name}</strong>
                  <span className="muted">{rule.is_active ? "Active" : "Paused"}</span>
                </div>
                <p className="muted">
                  {segmentName(rule.segment)} · {rule.mode === "automatic" ? "sends automatically" : "needs approval"}{" "}
                  · once per {rule.cooldown_days} days
                </p>
                <p>{rule.template}</p>
                <div className="row">
                  <button className="button secondary" onClick={() => edit(rule)} aria-label={`Edit ${rule.name}`}>
                    Edit
                  </button>
                  <button
                    className="button secondary"
                    onClick={() => toggle(rule)}
                    aria-label={`${rule.is_active ? "Pause" : "Resume"} ${rule.name}`}
                  >
                    {rule.is_active ? "Pause" : "Resume"}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <section className="card" aria-label="Rule form">
        <h2>{editing ? "Edit rule" : "New rule"}</h2>
        <form className="stack" onSubmit={save}>
          <label>
            Rule name
            <input value={form.name} onChange={change("name")} required />
          </label>
          <label>
            Send to segment
            <select value={form.segment} onChange={change("segment")}>
              {SEGMENTS.map(([value, name]) => (
                <option key={value} value={value}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Message
            <textarea rows="4" value={form.template} onChange={change("template")} required />
          </label>
          <p className="muted">
            You can use {"{name}"}, {"{visits}"}, {"{days_since_visit}"} and {"{restaurant}"}. "Reply STOP to
            opt out." is added to every message.
          </p>
          <label>
            Sending
            <select value={form.mode} onChange={change("mode")}>
              <option value="approval">Wait for my approval</option>
              <option value="automatic">Send automatically</option>
            </select>
          </label>
          <label>
            Message each guest at most once every (days)
            <input type="number" min="1" value={form.cooldown_days} onChange={change("cooldown_days")} required />
          </label>
          <div className="row">
            <button className="button" type="submit">
              {editing ? "Save rule" : "Add rule"}
            </button>
            {editing && (
              <button
                className="button secondary"
                type="button"
                onClick={() => {
                  setEditing(null);
                  setForm(EMPTY);
                }}
              >
                Cancel
              </button>
            )}
          </div>
        </form>
      </section>
    </div>
  );
}

import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { API_URL, getHealth } from "../api.js";
import { MODULES } from "../modules.js";

export default function Dashboard() {
  const [status, setStatus] = useState("checking");
  const [checkedAt, setCheckedAt] = useState(null);

  const checkBackend = useCallback(async (signal) => {
    setStatus("checking");
    try {
      const body = await getHealth(signal);
      setStatus(body.status === "ok" ? "ok" : "error");
    } catch (error) {
      if (error.name !== "AbortError") {
        setStatus("error");
      }
    }
    setCheckedAt(new Date());
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    checkBackend(controller.signal);
    return () => controller.abort();
  }, [checkBackend]);

  const statusText = {
    checking: "Checking...",
    ok: "Online",
    error: "Offline",
  }[status];

  return (
    <section>
      <h1>Dashboard</h1>

      <div className="card status-card">
        <div>
          <strong>Backend</strong>
          <span className={`badge badge-${status}`}>{statusText}</span>
          <p className="muted">
            {API_URL}
            {checkedAt && ` · checked ${checkedAt.toLocaleTimeString()}`}
          </p>
        </div>
        <button className="button secondary" onClick={() => checkBackend()}>
          Check again
        </button>
      </div>

      <h2>Modules</h2>
      <div className="grid">
        {MODULES.map((module) => (
          <Link key={module.path} to={`/${module.path}`} className="card module-card">
            <strong>{module.name}</strong>
            <span className="muted">{module.live ? "Live" : `Stage ${module.stage}`}</span>
            <p>{module.summary}</p>
          </Link>
        ))}
      </div>
    </section>
  );
}

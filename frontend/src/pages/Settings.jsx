import { useEffect, useState } from "react";
import { API_URL, getHealth } from "../api.js";
import { canManage, useAuth } from "../auth.jsx";
import ProfileSection from "../components/ProfileSection.jsx";
import StaffSection from "../components/StaffSection.jsx";

export default function Settings() {
  const { user } = useAuth();
  const [environment, setEnvironment] = useState("loading...");
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    getHealth(controller.signal)
      .then((body) => setEnvironment(body.environment))
      .catch((err) => {
        if (err.name !== "AbortError") {
          setError("Could not reach the backend.");
        }
      });
    return () => controller.abort();
  }, []);

  return (
    <section className="stack">
      <h1>Settings</h1>

      {canManage(user) && <ProfileSection />}
      {user?.role === "owner" && <StaffSection />}

      <div className="card">
        <h2>System</h2>
        <p>
          <strong>API URL:</strong> {API_URL}
        </p>
        <p>
          <strong>Environment:</strong> {environment}
        </p>
        {error && <p className="error">{error}</p>}
      </div>
    </section>
  );
}

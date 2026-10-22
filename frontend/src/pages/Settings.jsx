import { useEffect, useState } from "react";
import { API_URL, getHealth } from "../api.js";

export default function Settings() {
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
    <section>
      <h1>Settings</h1>
      <div className="card">
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

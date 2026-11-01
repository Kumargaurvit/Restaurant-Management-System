import { useEffect, useState } from "react";
import { API_URL, getHealth } from "../api.js";
import { useAuth } from "../auth.jsx";

function RestaurantName() {
  const { user, renameRestaurant } = useAuth();
  const [name, setName] = useState(user.restaurant_name ?? "");
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);

  async function save(event) {
    event.preventDefault();
    setMessage(null);
    setError(null);
    try {
      await renameRestaurant(name.trim());
      setMessage("Restaurant name saved.");
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <form className="card stack" onSubmit={save} aria-label="Restaurant name">
      <label>
        Restaurant name
        <input value={name} onChange={(e) => setName(e.target.value)} required />
      </label>
      <p className="muted">Shown at the top of the site, on bills and in messages to guests.</p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {message && <p role="status">{message}</p>}
      <button className="button" type="submit">
        Save name
      </button>
    </form>
  );
}

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
    <section>
      <h1>Settings</h1>
      {user.role === "owner" && <RestaurantName />}
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

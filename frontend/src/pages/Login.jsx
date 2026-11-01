import { useEffect, useState } from "react";
import { request } from "../api.js";
import { useAuth } from "../auth.jsx";

export default function Login() {
  const { login, setup } = useAuth();
  const [hasUsers, setHasUsers] = useState(null);
  const [mode, setMode] = useState(null); // "login" or "register"; chosen once we know if an owner exists
  const [restaurantName, setRestaurantName] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    request("/api/auth/status", { signal: controller.signal })
      .then((body) => {
        setHasUsers(body.has_users);
        setMode(body.has_users ? "login" : "register");
      })
      .catch((err) => {
        if (err.name !== "AbortError") setError("Cannot reach the server. Is the backend running?");
      });
    return () => controller.abort();
  }, []);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await setup(name, email, password, restaurantName.trim());
      }
    } catch (err) {
      setError(
        err.status === 409 && mode === "register"
          ? "An owner account already exists. Ask the owner to add you as staff, then sign in."
          : err.message,
      );
    } finally {
      setBusy(false);
    }
  }

  const isSetup = mode === "register";

  function switchTo(next) {
    setMode(next);
    setError(null);
  }

  return (
    <main className="auth-page">
      <form className="card auth-card" onSubmit={submit}>
        <h1>{isSetup ? (hasUsers ? "Register" : "Set up your restaurant") : "Sign in"}</h1>
        {isSetup && (
          <p className="muted">
            {hasUsers
              ? "Only the first owner can register. Staff accounts are added by the owner."
              : "Create the owner account. You can add staff afterwards."}
          </p>
        )}

        {isSetup && (
          <label>
            Restaurant name
            <input
              value={restaurantName}
              onChange={(e) => setRestaurantName(e.target.value)}
              required
              autoFocus
            />
          </label>
        )}
        {isSetup && (
          <label>
            Your name
            <input value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
        )}
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoFocus={!isSetup}
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={isSetup ? 8 : undefined}
            required
          />
        </label>

        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button className="button" type="submit" disabled={busy || mode === null}>
          {busy ? "Please wait..." : isSetup ? "Create owner account" : "Sign in"}
        </button>
        {mode !== null && (
          <button
            className="link-button"
            type="button"
            onClick={() => switchTo(isSetup ? "login" : "register")}
          >
            {isSetup ? "Already have an account? Sign in" : "New restaurant? Register"}
          </button>
        )}
      </form>
    </main>
  );
}

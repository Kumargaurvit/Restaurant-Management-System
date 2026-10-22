import { useEffect, useState } from "react";
import { request } from "../api.js";
import { useAuth } from "../auth.jsx";

export default function Login() {
  const { login, setup } = useAuth();
  const [hasUsers, setHasUsers] = useState(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    request("/api/auth/status", { signal: controller.signal })
      .then((body) => setHasUsers(body.has_users))
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
      if (hasUsers) {
        await login(email, password);
      } else {
        await setup(name, email, password);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const isSetup = hasUsers === false;

  return (
    <main className="auth-page">
      <form className="card auth-card" onSubmit={submit}>
        <h1>{isSetup ? "Set up your restaurant" : "Sign in"}</h1>
        {isSetup && (
          <p className="muted">Create the owner account. You can add staff afterwards.</p>
        )}

        {isSetup && (
          <label>
            Your name
            <input value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
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
        <button className="button" type="submit" disabled={busy || hasUsers === null}>
          {busy ? "Please wait..." : isSetup ? "Create owner account" : "Sign in"}
        </button>
      </form>
    </main>
  );
}

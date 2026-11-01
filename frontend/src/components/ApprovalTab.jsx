import { useCallback, useEffect, useState } from "react";
import { request } from "../api.js";

export default function ApprovalTab() {
  const [messages, setMessages] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      setMessages(await request("/api/retention/messages?status=pending"));
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function decide(message, action) {
    setError(null);
    try {
      await request(`/api/retention/messages/${message.id}/${action}`, { method: "POST" });
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section>
      <h2>Waiting for approval</h2>
      <p className="muted">Nothing is sent to a guest until you approve it here.</p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {messages === null ? (
        <p className="muted">Loading...</p>
      ) : messages.length === 0 ? (
        <p className="muted">No messages waiting.</p>
      ) : (
        <ul className="list" aria-label="Approval queue">
          {messages.map((message) => (
            <li key={message.id} className="card">
              <strong>{message.customer_name || "Guest"}</strong>{" "}
              <span className="muted">
                {message.phone} · {message.rule_name}
              </span>
              <p className="message-body">{message.body}</p>
              <div className="row">
                <button
                  className="button"
                  aria-label={`Approve message to ${message.customer_name || message.phone}`}
                  onClick={() => decide(message, "approve")}
                >
                  Approve &amp; send
                </button>
                <button
                  className="button secondary"
                  aria-label={`Reject message to ${message.customer_name || message.phone}`}
                  onClick={() => decide(message, "reject")}
                >
                  Reject
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

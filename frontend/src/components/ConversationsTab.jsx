import { useCallback, useEffect, useState } from "react";
import { request } from "../api.js";
import ChatThread from "./ChatThread.jsx";

const formatTime = (value) =>
  new Date(value).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });

export default function ConversationsTab() {
  const [conversations, setConversations] = useState(null);
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      setConversations(await request("/api/chat/conversations"));
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function open(id) {
    setError(null);
    try {
      setDetail(await request(`/api/chat/conversations/${id}`));
    } catch (err) {
      setError(err.message);
    }
  }

  async function resolve() {
    setError(null);
    try {
      await request(`/api/chat/conversations/${detail.id}/resolve`, { method: "POST" });
      await Promise.all([load(), open(detail.id)]);
    } catch (err) {
      setError(err.message);
    }
  }

  const waiting = conversations?.filter((c) => c.needs_human).length ?? 0;

  return (
    <div className="orders-layout">
      <div>
        <div className="row space-between">
          <h2>Conversations</h2>
          <button className="button secondary" onClick={load}>
            Refresh
          </button>
        </div>
        {waiting > 0 && (
          <p role="status" className="attention">
            {waiting} {waiting === 1 ? "guest needs" : "guests need"} a reply from a person.
          </p>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {conversations === null ? (
          <p className="muted">Loading...</p>
        ) : conversations.length === 0 ? (
          <p className="muted">No conversations yet. Guest chats appear here.</p>
        ) : (
          <ul className="list" aria-label="Conversations">
            {conversations.map((conversation) => (
              <li key={conversation.id}>
                <button className="list-button" onClick={() => open(conversation.id)}>
                  <strong>{conversation.customer_name || conversation.phone}</strong>{" "}
                  {conversation.customer_name && <span className="muted">{conversation.phone}</span>}
                  {conversation.needs_human && <span className="badge badge-error">Needs a person</span>}
                  <br />
                  <span className="muted">{conversation.last_message}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {detail && (
        <section className="card" aria-label="Conversation">
          <div className="row space-between">
            <h2>{detail.customer_name || detail.phone}</h2>
            <button className="button secondary" onClick={() => setDetail(null)}>
              Close
            </button>
          </div>
          <p className="muted">
            {detail.phone} · last message {formatTime(detail.last_message_at)}
          </p>
          {detail.needs_human && (
            <div className="attention" role="status">
              <strong>Needs a person.</strong> {detail.handoff_reason}
              <div>
                <button className="button" onClick={resolve}>
                  Mark as handled
                </button>
              </div>
              <p className="muted">
                Reply to this guest on WhatsApp directly. Replying from this screen is not available
                yet.
              </p>
            </div>
          )}
          <ChatThread messages={detail.messages} label="Chat messages" />
        </section>
      )}
    </div>
  );
}

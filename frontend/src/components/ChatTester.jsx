import { useState } from "react";
import { request } from "../api.js";
import ChatThread from "./ChatThread.jsx";

// Lets the owner talk to the bot as if they were a guest. Nothing is sent to WhatsApp.
export default function ChatTester() {
  const [phone, setPhone] = useState("9000000000");
  const [text, setText] = useState("");
  const [messages, setMessages] = useState([]);
  const [needsHuman, setNeedsHuman] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function send(event) {
    event.preventDefault();
    const sent = text.trim();
    if (!sent) return;
    setBusy(true);
    setError(null);
    setMessages((current) => [...current, { id: `u${current.length}`, role: "user", content: sent }]);
    setText("");
    try {
      const result = await request("/api/chat/simulate", { method: "POST", body: { phone, text: sent } });
      setMessages((current) => [
        ...current,
        { id: `a${current.length}`, role: "assistant", content: result.reply },
      ]);
      setNeedsHuman(result.needs_human);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card stack" aria-label="Test chat">
      <h2>Test the bot</h2>
      <p className="muted">
        Chat as a guest would. Nothing is sent to WhatsApp, but the conversation is saved. Use a
        mobile number that has bills to test "send my bill".
      </p>
      <label>
        Guest mobile number
        <input value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" />
      </label>

      <ChatThread messages={messages} label="Test conversation" />
      {needsHuman && (
        <p className="attention" role="status">
          The bot asked for a person to take over this chat.
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <form className="row" onSubmit={send}>
        <label className="grow">
          Message
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Is there space for 2?" />
        </label>
        <button className="button" type="submit" disabled={busy || text.trim() === ""}>
          Send
        </button>
      </form>
    </section>
  );
}

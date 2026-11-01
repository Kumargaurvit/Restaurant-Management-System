const formatTime = (value) =>
  value ? new Date(value).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "";

// A WhatsApp-style list of messages. Guest messages on the left, bot replies on the right.
export default function ChatThread({ messages, label = "Messages" }) {
  if (messages.length === 0) {
    return <p className="muted">No messages yet.</p>;
  }
  return (
    <ul className="thread" aria-label={label}>
      {messages.map((message) => (
        <li key={message.id} className={`bubble ${message.role}`}>
          <span className="bubble-who">{message.role === "user" ? "Guest" : "Bot"}</span>
          <span className="bubble-text">{message.content}</span>
          {message.created_at && <span className="bubble-time">{formatTime(message.created_at)}</span>}
        </li>
      ))}
    </ul>
  );
}

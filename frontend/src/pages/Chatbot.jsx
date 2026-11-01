import { useState } from "react";
import { canManage, useAuth } from "../auth.jsx";
import ChatTester from "../components/ChatTester.jsx";
import ConversationsTab from "../components/ConversationsTab.jsx";
import OffersTab from "../components/OffersTab.jsx";

const TABS = [
  { id: "offers", label: "Offers" },
  { id: "conversations", label: "Conversations" },
  { id: "test", label: "Test chat" },
];

export default function Chatbot() {
  const { user } = useAuth();
  const [tab, setTab] = useState("offers");

  if (!canManage(user)) {
    return (
      <section>
        <h1>WhatsApp Bot</h1>
        <p className="muted">Only owners and managers can manage the WhatsApp bot.</p>
      </section>
    );
  }

  return (
    <section>
      <h1>WhatsApp Bot</h1>
      <div className="tabs" role="tablist">
        {TABS.map((entry) => (
          <button
            key={entry.id}
            role="tab"
            aria-selected={tab === entry.id}
            className={`tab ${tab === entry.id ? "active" : ""}`}
            onClick={() => setTab(entry.id)}
          >
            {entry.label}
          </button>
        ))}
      </div>

      {tab === "offers" && <OffersTab />}
      {tab === "conversations" && <ConversationsTab />}
      {tab === "test" && <ChatTester />}
    </section>
  );
}

import { useState } from "react";
import { canManage, useAuth } from "../auth.jsx";
import ApprovalTab from "../components/ApprovalTab.jsx";
import CampaignReportTab from "../components/CampaignReportTab.jsx";
import RulesTab from "../components/RulesTab.jsx";
import SegmentsTab from "../components/SegmentsTab.jsx";
import Tabs from "../components/Tabs.jsx";

const TABS = [
  { id: "segments", label: "Segments" },
  { id: "rules", label: "Campaign rules" },
  { id: "approval", label: "Approval queue" },
  { id: "report", label: "Results" },
];

export default function Retention() {
  const { user } = useAuth();
  const [tab, setTab] = useState("segments");

  if (!canManage(user)) {
    return (
      <section>
        <h1>Retention</h1>
        <p className="muted">Customer retention is available to the owner and managers.</p>
      </section>
    );
  }

  return (
    <section>
      <h1>Retention</h1>
      <Tabs tabs={TABS} active={tab} onChange={setTab} />
      {tab === "segments" && <SegmentsTab />}
      {tab === "rules" && <RulesTab />}
      {tab === "approval" && <ApprovalTab />}
      {tab === "report" && <CampaignReportTab />}
    </section>
  );
}

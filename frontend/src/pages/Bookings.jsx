import { useState } from "react";
import { canManage, useAuth } from "../auth.jsx";
import BookingSettingsTab from "../components/BookingSettingsTab.jsx";
import BookingsTab from "../components/BookingsTab.jsx";
import Tabs from "../components/Tabs.jsx";

export default function Bookings() {
  const { user } = useAuth();
  const [tab, setTab] = useState("bookings");

  const tabs = [
    { id: "bookings", label: "Bookings" },
    ...(canManage(user) ? [{ id: "settings", label: "Hours & slots" }] : []),
  ];

  return (
    <section>
      <h1>Bookings</h1>
      <Tabs tabs={tabs} active={tab} onChange={setTab} />
      {tab === "bookings" && <BookingsTab />}
      {tab === "settings" && <BookingSettingsTab />}
    </section>
  );
}

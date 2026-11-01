import { Route, Routes } from "react-router-dom";
import { useAuth } from "./auth.jsx";
import Layout from "./components/Layout.jsx";
import Billing from "./pages/Billing.jsx";
import Chatbot from "./pages/Chatbot.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Login from "./pages/Login.jsx";
import ModulePage from "./pages/ModulePage.jsx";
import Settings from "./pages/Settings.jsx";

function RequireAuth() {
  const { user, phase } = useAuth();

  if (phase === "loading") {
    return <p className="muted loading">Loading...</p>;
  }
  if (!user) {
    return <Login />;
  }
  return <Layout />;
}

export default function App() {
  return (
    <Routes>
      <Route element={<RequireAuth />}>
        <Route index element={<Dashboard />} />
        <Route path="billing" element={<Billing />} />
        <Route path="chatbot" element={<Chatbot />} />
        <Route path="settings" element={<Settings />} />
        <Route path=":modulePath" element={<ModulePage />} />
      </Route>
    </Routes>
  );
}

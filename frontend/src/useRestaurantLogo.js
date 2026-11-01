import { useEffect, useState } from "react";
import { request } from "./api.js";

// Fired after the logo is saved so the header and bill preview update without a reload.
export const LOGO_EVENT = "rms:logo-changed";

export function useRestaurantLogo() {
  const [logo, setLogo] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    request("/api/restaurant/profile", { signal: controller.signal })
      .then((profile) => setLogo(profile.logo || ""))
      .catch(() => {});
    const onChange = (event) => setLogo(event.detail ?? "");
    window.addEventListener(LOGO_EVENT, onChange);
    return () => {
      controller.abort();
      window.removeEventListener(LOGO_EVENT, onChange);
    };
  }, []);

  return logo;
}

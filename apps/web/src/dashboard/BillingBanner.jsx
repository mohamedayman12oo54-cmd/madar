import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { billingApi } from "../lib/dashboardApi.js";
import { bannerFor } from "../lib/billing.js";

/**
 * Slim, dismissible-by-fixing notice at the top of every dashboard page. It only appears when the
 * server's entitlement decision calls for the teacher's attention; a fetch failure shows nothing
 * (a broken banner must never block teaching). It never links anywhere but the billing page.
 */
export default function BillingBanner() {
  const [sub, setSub] = useState(null);
  const { pathname } = useLocation();
  useEffect(() => {
    let live = true;
    billingApi
      .subscription()
      .then((s) => live && setSub(s))
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [pathname === "/app/billing"]); // eslint-disable-line react-hooks/exhaustive-deps
  const b = bannerFor(sub);
  if (!b || pathname === "/app/billing") return null;
  return (
    <div className="bl-strip" data-tone={b.tone} role="status">
      <span>{b.text}</span>
      <Link to="/app/billing" className="dash-linkish">
        {b.cta}
      </Link>
    </div>
  );
}

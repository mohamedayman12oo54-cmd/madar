import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { Bell, CheckCheck } from "lucide-react";
import { Btn, Banner } from "../auth/ui.jsx";
import { notificationsApi } from "../lib/notificationsApi.js";
import { ApiError } from "../lib/api.js";
import ComingSoon from "./ComingSoon.jsx";

const DELIVERY_LABEL = { pending: "قيد الإرسال", sent: "تم الإرسال", failed: "فشل الإرسال" };

function fmt(iso) {
  return new Date(iso).toLocaleString("ar-EG", { dateStyle: "medium", timeStyle: "short" });
}

export default function NotificationsPage() {
  const { refreshUnread } = useOutletContext() || {};
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState(null);

  const load = () => {
    setStatus((s) => (s === "ready" ? "ready" : "loading"));
    notificationsApi.list({ unread: unreadOnly })
      .then((data) => { setItems(data.results || data); setStatus("ready"); })
      .catch((e) => { setError(e instanceof ApiError ? e.message : "حدث خطأ أثناء تحميل البيانات."); setStatus("error"); });
  };

  useEffect(load, [unreadOnly]); // eslint-disable-line react-hooks/exhaustive-deps

  const markRead = async (n) => {
    const updated = await notificationsApi.markRead(n.id).catch(() => null);
    if (!updated) return;
    setItems((list) => (unreadOnly ? list.filter((x) => x.id !== n.id) : list.map((x) => (x.id === n.id ? updated : x))));
    refreshUnread?.();
  };

  return (
    <>
      <div className="dash-section-head">
        <h2>الإشعارات</h2>
        <Btn variant={unreadOnly ? "secondary" : "ghost"} onClick={() => setUnreadOnly((v) => !v)}>
          <CheckCheck size={16} /> {unreadOnly ? "عرض الكل" : "غير المقروءة فقط"}
        </Btn>
      </div>

      {status === "loading" && <p className="field-msg">جاري تحميل البيانات...</p>}
      {status === "error" && <Banner tone="err">{error}</Banner>}

      {status === "ready" && items.length === 0 && (
        <ComingSoon
          title={unreadOnly ? "لا توجد إشعارات غير مقروءة" : "لا توجد إشعارات بعد"}
          text="ستظهر هنا إشعارات فتح الجلسات وإعادة فتحها."
        />
      )}

      {status === "ready" && items.length > 0 && (
        <div className="dash-cards" style={{ gridTemplateColumns: "1fr" }}>
          {items.map((n) => (
            <div key={n.id} className={"dash-card dash-session-row" + (n.read_at ? "" : " dash-unread")}>
              <div className="dash-session-info" style={{ alignItems: "flex-start", flexDirection: "column", gap: 4 }}>
                <div className="k"><Bell size={14} /> {n.title}</div>
                <div>{n.body}</div>
                <div className="k">{fmt(n.created_at)}</div>
              </div>
              <div className="dash-session-actions">
                <span className={"dash-pill" + (n.delivery_status === "sent" ? " on" : "")}>{DELIVERY_LABEL[n.delivery_status]}</span>
                {!n.read_at && <Btn variant="ghost" onClick={() => markRead(n)}>تحديد كمقروء</Btn>}
              </div>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

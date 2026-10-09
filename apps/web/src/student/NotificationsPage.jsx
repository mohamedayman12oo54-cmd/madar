import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { Banner, Btn } from "../auth/ui.jsx";
import { studentApi } from "../lib/studentApi.js";
import { ApiError } from "../lib/api.js";
import { PageHeader, Empty, fmtDateTime } from "../dashboard/common.jsx";

export default function NotificationsPage() {
  const ctx = useOutletContext();
  const [items, setItems] = useState(null);
  const [err, setErr] = useState(null);
  const load = () => studentApi.notifications.list().then((d) => setItems(d.results)).catch((e) => setErr(e instanceof ApiError ? e.message : "تعذّر تحميل الإشعارات."));
  useEffect(() => { load(); }, []);

  const read = async (n) => {
    if (n.read) return;
    try { await studentApi.notifications.read(n.id); setItems((l) => l.map((x) => (x.id === n.id ? { ...x, read: true } : x))); ctx?.refreshUnread?.(); } catch { /* shown again on next load */ }
  };
  const readAll = async () => { try { await studentApi.notifications.readAll(); await load(); ctx?.refreshUnread?.(); } catch (e) { setErr(e instanceof ApiError ? e.message : "تعذّر التنفيذ."); } };
  const unread = items?.filter((n) => !n.read).length || 0;

  return (
    <>
      <PageHeader infoKey="student_notifications" title="الإشعارات">{unread > 0 && <Btn variant="ghost" onClick={readAll}>تعليم الكل كمقروء</Btn>}</PageHeader>
      {err && <Banner tone="err">{err}</Banner>}
      {!items && !err && <p className="field-msg">جاري التحميل...</p>}
      {items && items.length === 0 && <Empty title="لا توجد إشعارات" text="ستصلك هنا تنبيهات معلمك." />}
      <div className="list-rows">{items?.map((n) => (
        <button key={n.id} className={"list-row" + (n.read ? "" : " stu-unread")} style={{ textAlign: "start", cursor: "pointer" }} onClick={() => read(n)}>
          <div><strong>{n.title}</strong>{n.body && <div className="stat-sub">{n.body}</div>}<div className="stat-sub">{fmtDateTime(n.created_at)}</div></div>
          <span className="chip-s">{n.type_label}</span>
        </button>))}</div>
    </>
  );
}

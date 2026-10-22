import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import { Banner, Btn, Modal } from "../auth/ui.jsx";
import { studentApi } from "../lib/studentApi.js";
import { ApiError } from "../lib/api.js";
import { PageHeader, Empty, fmtDateTime } from "../dashboard/common.jsx";

export default function NotificationsPage() {
  const ctx = useOutletContext();
  const [items, setItems] = useState(null);
  const [err, setErr] = useState(null);
  const [open, setOpen] = useState(null);
  const load = () =>
    studentApi.notifications
      .list()
      .then((d) => setItems(d.results))
      .catch((e) => setErr(e instanceof ApiError ? e.message : "تعذّر تحميل الإشعارات."));
  useEffect(() => {
    load();
  }, []);

  const read = async (n) => {
    if (n.read) return;
    try {
      await studentApi.notifications.read(n.id);
      setItems((l) => l.map((x) => (x.id === n.id ? { ...x, read: true } : x)));
      ctx?.refreshUnread?.();
    } catch {
      /* shown again on next load */
    }
  };
  const readAll = async () => {
    try {
      await studentApi.notifications.readAll();
      await load();
      ctx?.refreshUnread?.();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "تعذّر التنفيذ.");
    }
  };
  const unread = items?.filter((n) => !n.read).length || 0;

  return (
    <>
      <PageHeader infoKey="student_notifications" title="الإشعارات">
        {unread > 0 && (
          <Btn variant="ghost" onClick={readAll}>
            تعليم الكل كمقروء
          </Btn>
        )}
      </PageHeader>
      {err && <Banner tone="err">{err}</Banner>}
      {!items && !err && <p className="field-msg">جاري التحميل...</p>}
      {items && items.length === 0 && (
        <Empty title="لا توجد إشعارات" text="ستصلك هنا تنبيهات معلمك." />
      )}
      <div className="list-rows">
        {items?.map((n) => (
          <div key={n.id} className={"list-row stu-note-row" + (n.read ? "" : " stu-unread")}>
            <button className="stu-note-main" onClick={() => read(n)}>
              <strong>{n.title}</strong>
              {n.body && <div className="stat-sub stu-note-preview">{n.body}</div>}
              <div className="stat-sub">{fmtDateTime(n.created_at)}</div>
            </button>
            <span className="row-actions">
              <span className="chip-s">{n.type_label}</span>
              <button
                className="mini-btn"
                onClick={() => {
                  read(n);
                  setOpen(n);
                }}
              >
                التفاصيل
              </button>
            </span>
          </div>
        ))}
      </div>

      {open && (
        <Modal
          size="md"
          title={open.title}
          text={
            open.details
              ? [...(open.details.grades || []), ...(open.details.groups || [])].join("، ")
              : open.type_label
          }
          onClose={() => setOpen(null)}
          footer={
            <Btn variant="ghost" onClick={() => setOpen(null)}>
              إغلاق
            </Btn>
          }
        >
          <p className="msg-body">{open.details?.body || open.body || "—"}</p>
          <div className="stat-sub">{fmtDateTime(open.details?.sent_at || open.created_at)}</div>
        </Modal>
      )}
    </>
  );
}

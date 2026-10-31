import { useEffect, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { Banner, Btn, Modal } from "../auth/ui.jsx";
import { studentApi } from "../lib/studentApi.js";
import { ApiError } from "../lib/api.js";
import { PageHeader, Empty, fmtDateTime } from "../dashboard/common.jsx";

// Where "open" leads, and what to call it — an exam must say "امتحان", never "فيديو". Only the folder name comes
// from this table; the path prefix is fixed in the JSX, so a server value can never become a router target.
const TARGET = {
  exam: { dir: "exams", label: "فتح الامتحان" },
  material: { dir: "materials", label: "فتح" },
  video: { dir: "videos", label: "مشاهدة" },
};
const TONE = { new_exam: "is-exam", new_material: "is-material", new_video: "is-video" };
const targetOf = (n) => {
  const t = n?.target && TARGET[n.target.kind];
  return t && Number.isInteger(n.target.id) ? { dir: t.dir, id: n.target.id, label: t.label } : null;
};

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
              <span className={"chip-s " + (TONE[n.type] || "")}>{n.type_label}</span>
              {targetOf(n) && (
                <Link className="mini-btn is-primary" to={`/learn/${targetOf(n).dir}/${targetOf(n).id}`} onClick={() => read(n)}>
                  {targetOf(n).label}
                </Link>
              )}
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
            <>
              {targetOf(open) && (
                <Link className="abtn abtn-primary" to={`/learn/${targetOf(open).dir}/${targetOf(open).id}`} onClick={() => setOpen(null)}>
                  {targetOf(open).label}
                </Link>
              )}
              <Btn variant="ghost" onClick={() => setOpen(null)}>
                إغلاق
              </Btn>
            </>
          }
        >
          <p className="msg-body">{open.details?.body || open.body || "—"}</p>
          <div className="stat-sub">{fmtDateTime(open.details?.sent_at || open.created_at)}</div>
        </Modal>
      )}
    </>
  );
}

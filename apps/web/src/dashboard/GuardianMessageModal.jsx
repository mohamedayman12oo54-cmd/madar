import { useEffect, useId, useState } from "react";
import { Field, TextInput, Btn, Banner, Modal } from "../auth/ui.jsx";
import { ApiError } from "../lib/api.js";
import { guardianMessagesApi } from "../lib/dashboardApi.js";
import { fmtDateTime } from "../lib/dates.js";
import { formatPhone } from "../lib/phone.js";
import "../parent/reply.css"; // .pp-reply: a guardian's answer, same look on both sides

/** Send a warning or a note about ONE student to that student's guardian. The guardian reads it in the
 *  guardian portal (it is not sent to the student). Shows what was already sent, newest first. */
export default function GuardianMessageModal({ enrollment, onClose, onRead }) {
  const formId = useId();
  const [kind, setKind] = useState("warning");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [err, setErr] = useState(null);
  const [fe, setFe] = useState({});
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState(null);
  const [sent, setSent] = useState([]);

  useEffect(() => {
    let alive = true;
    guardianMessagesApi
      .history(enrollment.id)
      .then((r) => {
        if (!alive) return;
        setSent(r.results || []);
        // Opening the conversation is reading its replies.
        if ((r.results || []).some((m) => m.replies?.some((x) => !x.read_at))) {
          guardianMessagesApi.readReplies(enrollment.id).then(() => onRead?.()).catch(() => {});
        }
      })
      .catch(() => {}); // the history is a convenience; sending must still work without it
    return () => {
      alive = false;
    };
  }, [enrollment.id]);

  const submit = async (ev) => {
    ev.preventDefault();
    setErr(null);
    setNotice(null);
    const errors = {};
    if (!title.trim()) errors.title = "اكتب عنوان الرسالة.";
    if (!body.trim()) errors.body = "اكتب نص الرسالة.";
    setFe(errors);
    if (Object.keys(errors).length) return;
    setSaving(true);
    try {
      const m = await guardianMessagesApi.send({
        enrollment_id: enrollment.id,
        kind,
        title: title.trim(),
        body: body.trim(),
      });
      setSent((l) => [m, ...l]);
      setTitle("");
      setBody("");
      setNotice(
        m.guardian_can_view
          ? { tone: "ok", text: "تم الإرسال. ستظهر الرسالة لولي الأمر في بوابة المتابعة." }
          : {
              tone: "info",
              text: "تم حفظ الرسالة، لكن ولي الأمر لن يراها قبل أن يفعّل الطالب حسابه.",
            }
      );
    } catch (e) {
      if (e instanceof ApiError && e.fields) setFe(e.fields);
      else setErr(e instanceof ApiError ? e.message : "تعذّر إرسال الرسالة.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      size="lg"
      title={`رسالة لولي أمر ${enrollment.student.name}`}
      text={`تصل إلى ${enrollment.parent_name || "ولي الأمر"} ${formatPhone(enrollment.parent_phone)} في بوابة المتابعة، ولا تصل إلى الطالب.`}
      onClose={onClose}
      footer={
        <>
          <Btn variant="ghost" type="button" onClick={onClose}>
            إغلاق
          </Btn>
          <Btn type="submit" form={formId} loading={saving} loadingText="جارٍ الإرسال…">
            إرسال
          </Btn>
        </>
      }
    >
      <form id={formId} onSubmit={submit} className="dash-form" noValidate>
        {err && <Banner tone="err">{err}</Banner>}
        {notice && <Banner tone={notice.tone}>{notice.text}</Banner>}
        <Field label="النوع">
          <select className="inp" value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="warning">تحذير</option>
            <option value="note">ملاحظة</option>
          </select>
        </Field>
        <Field label="العنوان" required error={fe.title}>
          <TextInput
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={150}
            error={fe.title}
          />
        </Field>
        <Field label="نص الرسالة" required error={fe.body}>
          <textarea
            className={"inp" + (fe.body ? " err" : "")}
            rows={4}
            maxLength={1000}
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
        </Field>
      </form>

      {sent.length > 0 && (
        <section style={{ marginBlockStart: 18 }}>
          <h4>الرسائل السابقة</h4>
          <div className="list-rows">
            {sent.map((m) => (
              <div key={m.id} className="list-row">
                <div>
                  <strong>{m.title}</strong>
                  {m.automatic && <span className="chip-s"> تلقائي</span>}
                  <div className="stat-sub" style={{ whiteSpace: "pre-wrap" }}>
                    {m.body}
                  </div>
                  <div className="stat-sub">
                    {fmtDateTime(m.created_at)} •{" "}
                    {m.read_at ? `قرأها ولي الأمر ${fmtDateTime(m.read_at)}` : "لم تُقرأ بعد"}
                  </div>
                  {(m.replies || []).map((r) => (
                    <div key={r.id} className="pp-reply">
                      <small>رد ولي الأمر • {fmtDateTime(r.created_at)}</small>
                      <div style={{ whiteSpace: "pre-wrap" }}>{r.body}</div>
                    </div>
                  ))}
                </div>
                <span className={"chip-s " + (m.kind === "warning" ? "bad" : "")}>{m.kind_label}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </Modal>
  );
}

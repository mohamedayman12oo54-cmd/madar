import { useState } from "react";
import { Btn } from "../auth/ui.jsx";
import { ApiError } from "../lib/api.js";
import "./reply.css";

/** Collapsed until the guardian chooses to answer, so the portal stays a plain report by default. */
export default function ReplyBox({ onSend, onSent }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  if (!open) {
    return (
      <button type="button" className="mini-btn no-print" onClick={() => setOpen(true)}>
        رد على المدرس
      </button>
    );
  }
  const send = async (e) => {
    e.preventDefault();
    if (!text.trim()) {
      setErr("اكتب ردك.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      onSent(await onSend(text.trim()));
      setText("");
      setOpen(false);
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "تعذّر إرسال الرد.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={send} className="pp-replybox no-print" noValidate>
      <textarea
        className="inp"
        rows={3}
        maxLength={500}
        aria-label="ردك على المدرس"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      {err && <div className="field-msg err">{err}</div>}
      <div className="pp-replybox-actions">
        <Btn type="submit" loading={busy} loadingText="جارٍ الإرسال…">
          إرسال الرد
        </Btn>
        <Btn variant="ghost" type="button" onClick={() => setOpen(false)}>
          إلغاء
        </Btn>
      </div>
    </form>
  );
}

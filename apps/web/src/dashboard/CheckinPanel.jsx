/**
 * Self check-in panel (teacher, scanner page): generates the QR students scan to mark THEMSELVES
 * present in the selected open session.
 *
 * The QR carries only an opaque link (/checkin/<token>); the six-digit code is shown beside it for the
 * teacher to announce, so a photo of the QR alone cannot mark anyone present. Everything that matters
 * (membership, the code, expiry, "present only") is enforced by the server.
 */
import { useCallback, useEffect, useState } from "react";
import QRCode from "qrcode";
import { Check, Copy, Expand, QrCode, RefreshCw, Users, X } from "lucide-react";
import { Btn, Banner } from "../auth/ui.jsx";
import { schedulingApi } from "../lib/dashboardApi.js";
import { ApiError } from "../lib/api.js";
import { qrImageSrc } from "../lib/qr.js";
import { fmtTime } from "../lib/dates.js";

const POLL_MS = 8000;

export const checkinUrl = (token) =>
  `${window.location.origin}/checkin/${encodeURIComponent(token)}`;

export default function CheckinPanel({ sessionId }) {
  const [link, setLink] = useState(null);
  const [svg, setSvg] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [copied, setCopied] = useState(false);
  const [full, setFull] = useState(false);

  const load = useCallback(async () => {
    if (!sessionId) {
      setLink(null);
      return;
    }
    try {
      setLink((await schedulingApi.sessions.checkin.get(sessionId)).link);
    } catch {
      /* the next poll will retry; a failed read is not worth interrupting the teacher */
    }
  }, [sessionId]);

  useEffect(() => {
    setErr(null);
    load();
  }, [load]);

  // The attendee count keeps moving while the class scans in.
  useEffect(() => {
    if (!sessionId || !link) return undefined;
    const t = setInterval(load, POLL_MS);
    return () => clearInterval(t);
  }, [sessionId, link, load]);

  const token = link?.token;
  useEffect(() => {
    let alive = true;
    if (!token) {
      setSvg("");
      return undefined;
    }
    QRCode.toString(checkinUrl(token), {
      type: "svg",
      margin: 1,
      width: 260,
      errorCorrectionLevel: "M",
    })
      .then((out) => alive && setSvg(out))
      .catch(() => alive && setSvg(""));
    return () => {
      alive = false;
    };
  }, [token]);

  useEffect(() => {
    if (!full) return undefined;
    const onKey = (e) => e.key === "Escape" && setFull(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [full]);

  const run = async (fn) => {
    setBusy(true);
    setErr(null);
    try {
      await fn();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "تعذّر تنفيذ العملية.");
    } finally {
      setBusy(false);
    }
  };

  const create = () =>
    run(async () => setLink((await schedulingApi.sessions.checkin.create(sessionId)).link));
  const revoke = () =>
    run(async () => {
      await schedulingApi.sessions.checkin.revoke(sessionId);
      setLink(null);
      setFull(false);
    });

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(checkinUrl(link.token));
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard unavailable */
    }
  };

  const qrSrc = qrImageSrc(svg);
  const spaced = link ? `${link.code.slice(0, 3)} ${link.code.slice(3)}` : "";

  return (
    <section className="ck" aria-labelledby="ck-title">
      <header className="ck-head">
        <span className="ck-ic" aria-hidden="true">
          <QrCode size={18} />
        </span>
        <div>
          <h2 id="ck-title">تسجيل الحضور بالرمز</h2>
          <p>يمسح الطلاب الرمز بكاميرا هواتفهم ويسجّلون حضورهم بأنفسهم.</p>
        </div>
      </header>

      {err && <Banner tone="err">{err}</Banner>}

      {!sessionId ? (
        <p className="ck-empty">اختر جلسة مفتوحة لإنشاء رمز الحضور الخاص بها.</p>
      ) : !link ? (
        <div className="ck-start">
          <p>
            سيحتاج الطالب إلى <strong>رقم هاتفه على المنصة</strong> و<strong>كود من ٦ أرقام</strong>{" "}
            تعلنه أنت داخل الحصة. لا يستطيع إلا تسجيل حضوره في هذه الجلسة.
          </p>
          <Btn onClick={create} loading={busy} loadingText="جاري الإنشاء…">
            <QrCode size={16} /> إنشاء رمز الحضور
          </Btn>
        </div>
      ) : (
        <div className="ck-live">
          <div className="ck-qr">
            {qrSrc ? (
              <img src={qrSrc} alt="رمز QR لتسجيل الحضور" width={220} height={220} />
            ) : (
              <p className="field-msg">تعذّر رسم الرمز.</p>
            )}
          </div>
          <div className="ck-code">
            <span className="ck-code-label">كود الحصة — أعلنه للطلاب</span>
            <strong dir="ltr" aria-label={`الكود ${link.code.split("").join(" ")}`}>
              {spaced}
            </strong>
          </div>
          <div className="ck-stats">
            <span>
              <Users size={14} aria-hidden="true" /> سجّل حضوره: <b>{link.checked_in_count}</b>
            </span>
            <span>ينتهي {fmtTime(link.expires_at)}</span>
          </div>
          <div className="ck-actions">
            <button type="button" className="mini-btn" onClick={() => setFull(true)}>
              <Expand size={14} /> عرض كبير
            </button>
            <button type="button" className="mini-btn" onClick={copy}>
              {copied ? <Check size={14} /> : <Copy size={14} />}{" "}
              {copied ? "تم النسخ" : "نسخ الرابط"}
            </button>
            <button type="button" className="mini-btn" onClick={create} disabled={busy}>
              <RefreshCw size={14} /> رمز جديد
            </button>
            <button type="button" className="mini-btn danger" onClick={revoke} disabled={busy}>
              <X size={14} /> إيقاف
            </button>
          </div>
          <p className="ck-note">
            إنشاء رمز جديد يُلغي الرمز السابق فورًا. يتوقف الرمز تلقائيًا عند إغلاق الجلسة.
          </p>
        </div>
      )}

      {full && link && (
        <div className="ck-full" role="dialog" aria-modal="true" aria-label="رمز الحضور بحجم كبير">
          <button
            type="button"
            className="ck-full-x"
            onClick={() => setFull(false)}
            aria-label="إغلاق"
          >
            <X size={22} />
          </button>
          <div className="ck-full-card">
            <p>امسح الرمز ثم أدخل رقم هاتفك والكود</p>
            {qrSrc && <img src={qrSrc} alt="رمز QR لتسجيل الحضور" />}
            <strong dir="ltr">{spaced}</strong>
            <span>
              سجّل حضوره حتى الآن: <b>{link.checked_in_count}</b>
            </span>
          </div>
        </div>
      )}
    </section>
  );
}

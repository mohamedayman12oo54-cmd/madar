import { useCallback, useEffect, useState } from "react";
import QRCode from "qrcode";
import { Check, Copy, RefreshCw, Trash2 } from "lucide-react";
import { Btn, Banner, Modal } from "../auth/ui.jsx";
import { registrationApi } from "../lib/academicsApi.js";
import { ApiError } from "../lib/api.js";
import { qrImageSrc } from "../lib/qr.js";
import { fmtDate } from "./common.jsx";

export const registrationUrl = (token) =>
  `${window.location.origin}/register/${encodeURIComponent(token)}`;

/**
 * Teacher: create the QR students scan to REGISTER THEMSELVES (name, phone, grade, one group, guardian).
 * The link is a revocable, expiring secret; regenerating it kills the previous one at once. The badge
 * code of a self-registered student is never shown to the student: the teacher hands it over.
 */
export default function RegistrationQrModal({ onClose }) {
  const [link, setLink] = useState(undefined); // undefined = loading, null = none
  const [svg, setSvg] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    try {
      setLink((await registrationApi.get()).link);
    } catch (e) {
      setLink(null);
      setErr(e instanceof ApiError ? e.message : "تعذّر تحميل الرمز.");
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const token = link?.token;
  useEffect(() => {
    let alive = true;
    if (!token) {
      setSvg("");
      return undefined;
    }
    QRCode.toString(registrationUrl(token), { type: "svg", margin: 1, width: 260, errorCorrectionLevel: "M" })
      .then((out) => alive && setSvg(out))
      .catch(() => alive && setSvg(""));
    return () => {
      alive = false;
    };
  }, [token]);

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
  const create = () => run(async () => setLink((await registrationApi.create()).link));
  const revoke = () =>
    run(async () => {
      await registrationApi.revoke();
      setLink(null);
    });
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(registrationUrl(link.token));
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard unavailable */
    }
  };

  const qrSrc = qrImageSrc(svg);

  return (
    <Modal
      size="md"
      title="تسجيل الطلاب برمز QR"
      text="يمسح الطالب الرمز بكاميرا هاتفه، ويسجّل اسمه ورقمه وصفه ومجموعته وبيانات ولي أمره، فيُضاف إلى المنصة تلقائيًا."
      onClose={onClose}
    >
      {err && <Banner tone="err">{err}</Banner>}
      {link === undefined ? (
        <p className="rq-note">جارٍ التحميل…</p>
      ) : !link ? (
        <div className="rq-start">
          <p className="rq-note">
            الطالب المسجَّل بهذه الطريقة يظهر في قائمة الطلاب بمجموعة واحدة، ولا يرى كود الطالب. ستعطيه الكود
            بنفسك بعد ذلك ليفعّل حسابه.
          </p>
          <Btn onClick={create} loading={busy} loadingText="جاري الإنشاء…">
            إنشاء رمز التسجيل
          </Btn>
        </div>
      ) : (
        <div className="rq-live">
          {qrSrc && <img className="rq-qr" src={qrSrc} alt="رمز QR لتسجيل الطلاب" width={240} height={240} />}
          <p className="rq-meta">
            صالح حتى {fmtDate(link.expires_at)} · سجّل به {Number(link.registered_count).toLocaleString("ar-EG")} طالب
          </p>
          <div className="rq-actions">
            <Btn variant="ghost" onClick={copy}>
              {copied ? <Check size={15} /> : <Copy size={15} />} {copied ? "تم النسخ" : "نسخ الرابط"}
            </Btn>
            <Btn variant="ghost" onClick={create} loading={busy}>
              <RefreshCw size={15} /> رمز جديد
            </Btn>
            <Btn variant="ghost" onClick={revoke} disabled={busy}>
              <Trash2 size={15} /> إيقاف التسجيل
            </Btn>
          </div>
          <p className="rq-note">«رمز جديد» يُبطل الرمز السابق فورًا. «إيقاف التسجيل» يُغلق الرابط حتى تنشئ رمزًا آخر.</p>
        </div>
      )}
    </Modal>
  );
}

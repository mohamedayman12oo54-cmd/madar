/**
 * Teacher QR scanner — scan a student badge, then pick one of three actions:
 * attendance, recitation, monthly fees.
 *
 * Camera decoding uses the browser's built-in BarcodeDetector where it exists and falls back to
 * jsQR (small, pure-JS, no network) elsewhere. The REAR camera is requested first. Typing/pasting
 * the badge code always remains available.
 *
 * Nothing here maps a code to a student: the opaque token is sent to the
 * server, which resolves it inside the active environment only. The client
 * also never sends a fee amount — the Grade owns it (INV-5).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import jsQR from "jsqr";
import {
  ScanLine,
  Camera,
  CameraOff,
  UserRound,
  Check,
  X,
  BookOpenCheck,
  Wallet,
  RotateCcw,
} from "lucide-react";
import { Btn, Banner, Field } from "../auth/ui.jsx";
import { scannerApi, schedulingApi } from "../lib/dashboardApi.js";
import { ApiError } from "../lib/api.js";
import { PageHeader, Empty, fmtMonth } from "./common.jsx";
import CheckinPanel from "./CheckinPanel.jsx";

const ATT = { present: "حاضر", absent: "غائب" };
const REC = { studied: "ذاكر", not_studied: "لم يذاكر" };

export default function ScannerPage() {
  const [sessions, setSessions] = useState([]);
  const [sessionId, setSessionId] = useState("");
  const [token, setToken] = useState("");
  const [student, setStudent] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [ok, setOk] = useState(null);
  const [camOn, setCamOn] = useState(false);
  const [camError, setCamError] = useState(null);

  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const loopRef = useRef(null);
  const lastRef = useRef("");

  // Only OPEN sessions can take records, so only offer those.
  useEffect(() => {
    schedulingApi.sessions
      .list({ status: "open" })
      .then((d) => {
        const rows = d.results || d || [];
        setSessions(rows);
        if (rows.length === 1) setSessionId(String(rows[0].id));
      })
      .catch(() => {});
  }, []);

  const stopCamera = useCallback(() => {
    clearInterval(loopRef.current);
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    setCamOn(false);
  }, []);

  useEffect(() => stopCamera, [stopCamera]);

  const resolve = useCallback(
    async (raw) => {
      const code = (raw || "").trim();
      if (!code || busy) return;
      setBusy(true);
      setErr(null);
      setOk(null);
      try {
        setStudent(await scannerApi.resolve(code, sessionId || null));
        setToken(code);
      } catch (e) {
        setStudent(null);
        setErr(
          e instanceof ApiError && e.status === 404
            ? "رمز غير معروف في بيئتك. تأكد أنه بادچ أحد طلابك."
            : e?.message || "تعذّر قراءة الرمز."
        );
      } finally {
        setBusy(false);
      }
    },
    [busy, sessionId]
  );

  // Rear camera first (facingMode "environment"), then any camera. The <video> element is ALWAYS in
  // the DOM (see the stage below) so the stream always has somewhere to render.
  const openStream = async () => {
    const tries = [
      { video: { facingMode: { exact: "environment" } }, audio: false },
      { video: { facingMode: { ideal: "environment" } }, audio: false },
      { video: true, audio: false },
    ];
    let last;
    for (const constraints of tries) {
      try {
        return await navigator.mediaDevices.getUserMedia(constraints);
      } catch (e) {
        last = e;
        if (e?.name === "NotAllowedError" || e?.name === "SecurityError") break;
      }
    }
    throw last;
  };

  const startCamera = useCallback(async () => {
    setCamError(null);
    if (!navigator.mediaDevices?.getUserMedia) {
      setCamError("الكاميرا تحتاج اتصالًا آمنًا (HTTPS) ومتصفحًا حديثًا. استخدم إدخال الرمز يدويًا.");
      return;
    }
    try {
      const stream = await openStream();
      streamRef.current = stream;
      const video = videoRef.current;
      video.srcObject = stream;
      await video.play();
      setCamOn(true);

      // Native detector where it exists; jsQR (pure JS) everywhere else, so the camera works on
      // desktop Chrome, Safari and Firefox too.
      const native = "BarcodeDetector" in window ? new window.BarcodeDetector({ formats: ["qr_code"] }) : null;
      const canvas = document.createElement("canvas");
      const ctx = canvas.getContext("2d", { willReadFrequently: true });
      const onHit = (value) => {
        // Ignore the same code re-detected frame after frame.
        if (value && value !== lastRef.current) {
          lastRef.current = value;
          resolve(value);
        }
      };
      loopRef.current = setInterval(async () => {
        const v = videoRef.current;
        if (!v || v.readyState < 2 || !v.videoWidth) return;
        try {
          if (native) {
            const [hit] = await native.detect(v);
            onHit(hit?.rawValue);
          } else {
            const w = Math.min(640, v.videoWidth);
            canvas.width = w;
            canvas.height = Math.round((v.videoHeight / v.videoWidth) * w);
            ctx.drawImage(v, 0, 0, canvas.width, canvas.height);
            const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
            onHit(jsQR(img.data, img.width, img.height, { inversionAttempts: "dontInvert" })?.data);
          }
        } catch {
          /* a dropped frame is not an error worth surfacing */
        }
      }, 300);
    } catch (e) {
      stopCamera();
      setCamError(
        e?.name === "NotAllowedError"
          ? "تم رفض إذن الكاميرا. فعّله من إعدادات المتصفح ثم أعد المحاولة، أو أدخل الرمز يدويًا."
          : e?.name === "NotFoundError"
          ? "لا توجد كاميرا متاحة على هذا الجهاز. أدخل الرمز يدويًا."
          : "تعذّر فتح الكاميرا. تأكد أنها غير مستخدمة في تطبيق آخر، أو أدخل الرمز يدويًا."
      );
    }
  }, [resolve, stopCamera]);

  const act = async (fn, successText) => {
    setBusy(true);
    setErr(null);
    setOk(null);
    try {
      setStudent(await fn());
      setOk(successText);
    } catch (e) {
      setErr(e?.message || "تعذّر تنفيذ العملية.");
    } finally {
      setBusy(false);
    }
  };

  const clear = () => {
    setStudent(null);
    setToken("");
    setOk(null);
    setErr(null);
    lastRef.current = "";
  };
  const needSession = !sessionId;

  return (
    <>
      <PageHeader infoKey="scan" title="مسح رمز الطالب" />
      <div className="scan-layout">
        <div className="scan-top">
          <Field
            label="الجلسة الحالية"
            hint="التسجيل يتم داخل جلسة مفتوحة. الرسوم الشهرية لا تحتاج جلسة."
          >
            <select
              className="inp"
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
            >
              <option value="">— اختر جلسة مفتوحة —</option>
              {sessions.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.group_name || s.group?.name || `جلسة #${s.id}`}
                </option>
              ))}
            </select>
          </Field>

          <div className={`scan-stage${camOn ? " is-live" : ""}`}>
            <video ref={videoRef} className="scan-video" muted playsInline autoPlay />
            {!camOn && (
              <div className="scan-placeholder">
                <ScanLine size={30} />
                <p>وجّه الكاميرا نحو بادچ الطالب</p>
              </div>
            )}
          </div>

          <div className="scan-controls">
            {camOn ? (
              <Btn variant="ghost" onClick={stopCamera}>
                <CameraOff size={16} /> إيقاف الكاميرا
              </Btn>
            ) : (
              <Btn onClick={startCamera}>
                <Camera size={16} /> تشغيل الكاميرا
              </Btn>
            )}
            {student && (
              <Btn variant="ghost" onClick={clear}>
                <RotateCcw size={14} /> مسح جديد
              </Btn>
            )}
          </div>

          {camError && <Banner tone="warn">{camError}</Banner>}

          <form
            className="scan-manual"
            onSubmit={(e) => {
              e.preventDefault();
              resolve(token);
            }}
          >
            <input
              className="inp code-input"
              value={token}
              maxLength={8}
              inputMode="text"
              autoCapitalize="characters"
              spellCheck={false}
              placeholder="أو اكتب رمز الطالب"
              onChange={(e) => setToken(e.target.value.toUpperCase())}
            />
            <Btn type="submit" loading={busy} disabled={!token.trim()}>
              بحث
            </Btn>
          </form>
        </div>

        <div className="scan-panel">
          <CheckinPanel sessionId={sessionId} />
        </div>

        <div className="scan-results">
          {err && <Banner tone="err">{err}</Banner>}
          {ok && <Banner tone="ok">{ok}</Banner>}

          {!student ? (
            <Empty
              title="لم يُمسح أي رمز بعد"
              text="شغّل الكاميرا وامسح بادچ الطالب، أو أدخل الرمز يدويًا."
            />
          ) : (
            <section className="scan-card">
              <header className="scan-id">
                <span className="scan-avatar">
                  <UserRound size={20} />
                </span>
                <div className="scan-id-main">
                  <strong>{student.name}</strong>
                  <div className="stat-sub">
                    {student.grade} · رسوم الشهر {student.fee_amount}
                  </div>
                </div>
                {!student.is_active && <span className="chip-s bad">غير نشط</span>}
              </header>

              <dl className="scan-state">
                <div>
                  <dt>الحضور</dt>
                  <dd>{ATT[student.attendance] || "—"}</dd>
                </div>
                <div>
                  <dt>التسميع</dt>
                  <dd>{REC[student.recitation] || "—"}</dd>
                </div>
                <div>
                  <dt>رسوم {fmtMonth(student.month)}</dt>
                  <dd>{student.payment_status === "paid" ? "مدفوعة" : "غير مدفوعة"}</dd>
                </div>
              </dl>

              {student.guest && (
                <Banner tone="info">
                  ضيف في هذه الجلسة (من مجموعة أخرى) —{" "}
                  {student.guest.home_session
                    ? `سيُسجَّل تلقائيًا في جلسة مجموعته: ${student.guest.home_session.group}`
                    : "سيُسجَّل تلقائيًا في أول جلسة تُفتح لمجموعته"}
                  .
                </Banner>
              )}
              {needSession && (
                <Banner tone="warn">اختر جلسة مفتوحة لتسجيل الحضور أو التسميع.</Banner>
              )}

              <div className="scan-actions">
                <Btn
                  disabled={busy || needSession}
                  onClick={() =>
                    act(() => scannerApi.attendance(token, sessionId), "تم تسجيل الحضور.")
                  }
                >
                  <Check size={16} /> تسجيل الحضور
                </Btn>
                <Btn
                  variant="ghost"
                  disabled={busy || needSession}
                  onClick={() =>
                    act(() => scannerApi.attendance(token, sessionId, "absent"), "تم تسجيل الغياب.")
                  }
                >
                  <X size={16} /> غياب
                </Btn>
              </div>

              <div className="scan-actions">
                <Btn
                  variant="ghost"
                  disabled={busy || needSession}
                  onClick={() =>
                    act(
                      () => scannerApi.recitation(token, sessionId, "studied"),
                      "تم التسجيل: ذاكر."
                    )
                  }
                >
                  <BookOpenCheck size={16} /> ذاكر
                </Btn>
                <Btn
                  variant="ghost"
                  disabled={busy || needSession}
                  onClick={() =>
                    act(
                      () => scannerApi.recitation(token, sessionId, "not_studied"),
                      "تم التسجيل: لم يذاكر."
                    )
                  }
                >
                  <BookOpenCheck size={16} /> لم يذاكر
                </Btn>
              </div>

              <div className="scan-actions">
                <Btn
                  variant="ghost"
                  disabled={busy || student.payment_status === "paid"}
                  onClick={() => act(() => scannerApi.payment(token), "تم تسجيل سداد رسوم الشهر.")}
                >
                  <Wallet size={16} />{" "}
                  {student.payment_status === "paid" ? "الرسوم مسجّلة" : "تسجيل سداد الرسوم"}
                </Btn>
              </div>
            </section>
          )}
        </div>
      </div>
    </>
  );
}

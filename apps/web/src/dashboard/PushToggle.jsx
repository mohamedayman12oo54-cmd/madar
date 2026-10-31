import { useEffect, useState } from "react";
import { BellRing } from "lucide-react";
import { Btn, Banner } from "../auth/ui.jsx";
import { useSession } from "../state/session.jsx";
import { currentSubscription, disablePush, enablePush, needsInstallOnIos, pushSupported } from "../lib/push.js";

const ERR = {
  unsupported: "متصفحك لا يدعم الإشعارات.",
  server_off: "الإشعارات غير مفعّلة على الخادم حاليًا.",
  denied: "تم رفض إذن الإشعارات. فعّله من إعدادات المتصفح أو الموقع ثم أعد المحاولة.",
};

/** "Notifications on this device" card, used in both teacher and student settings. */
export default function PushToggle() {
  const { user } = useSession();
  const [on, setOn] = useState(null); // null = checking
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const supported = pushSupported();
  const iosNeedsInstall = supported && needsInstallOnIos();

  useEffect(() => {
    if (!supported) return;
    currentSubscription().then((s) => setOn(Boolean(s) && Notification.permission === "granted")).catch(() => setOn(false));
  }, [supported]);

  const toggle = async () => {
    setBusy(true);
    setErr(null);
    try {
      if (on) {
        await disablePush(user.id);
        setOn(false);
      } else {
        await enablePush(user.id);
        setOn(true);
      }
    } catch (e) {
      setErr(ERR[e?.code] || e?.message || "تعذّر تغيير الإعداد.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="dash-card" style={{ marginBlockEnd: 18 }}>
      <h3 style={{ marginBlockEnd: 8, display: "flex", gap: 8, alignItems: "center" }}><BellRing size={18} /> إشعارات الجهاز</h3>
      <p className="stat-sub" style={{ marginBlockEnd: 12 }}>
        استقبل إشعارات مدار على هذا الجهاز حتى لو كان التطبيق مغلقًا.
      </p>
      {err && <Banner tone="err">{err}</Banner>}
      {!supported && <Banner tone="info">متصفحك لا يدعم إشعارات الويب. جرّب Chrome أو Safari الحديث.</Banner>}
      {iosNeedsInstall && (
        <Banner tone="info">على الآيفون: افتح الموقع في Safari ← زر المشاركة ← «إضافة إلى الشاشة الرئيسية»، ثم افتح التطبيق من الأيقونة وفعّل الإشعارات.</Banner>
      )}
      {supported && !iosNeedsInstall && (
        <Btn variant={on ? "ghost" : undefined} onClick={toggle} loading={busy} disabled={on === null}>
          {on ? "إيقاف الإشعارات على هذا الجهاز" : "تفعيل الإشعارات على هذا الجهاز"}
        </Btn>
      )}
    </section>
  );
}

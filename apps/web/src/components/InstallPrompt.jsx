/**
 * "Install Madar" invitation.
 *
 * Two very different paths, because the platforms differ:
 *
 *  - Chrome / Edge / Android fire `beforeinstallprompt`. We capture it,
 *    suppress the browser's own mini-bar, and show our own card so the ask
 *    appears in Arabic and on brand.
 *  - iOS Safari has NO install API. The only route is Share → Add to Home
 *    Screen, so there we show instructions instead of a button that could not
 *    work.
 *
 * It never nags: dismissing stores a flag, and the card stays hidden while the
 * app is already running installed (`display-mode: standalone`).
 */
import { useCallback, useEffect, useState } from "react";
import { Download, Share, Plus, X } from "lucide-react";

const DISMISSED_KEY = "madar.install.dismissed";
const DISMISS_DAYS = 14;

const isStandalone = () =>
  window.matchMedia?.("(display-mode: standalone)")?.matches ||
  window.navigator.standalone === true;

const isIOS = () => /iphone|ipad|ipod/i.test(window.navigator.userAgent) && !window.MSStream;

function recentlyDismissed() {
  try {
    const at = Number(localStorage.getItem(DISMISSED_KEY) || 0);
    return at > 0 && Date.now() - at < DISMISS_DAYS * 864e5;
  } catch {
    return false; // private mode: just show it
  }
}

export default function InstallPrompt() {
  const [deferred, setDeferred] = useState(null);
  const [show, setShow] = useState(false);
  const [iosHelp, setIosHelp] = useState(false);

  useEffect(() => {
    if (isStandalone() || recentlyDismissed()) return undefined;

    const onBeforeInstall = (e) => {
      e.preventDefault(); // suppress the browser's own bar
      setDeferred(e);
      setShow(true);
    };
    window.addEventListener("beforeinstallprompt", onBeforeInstall);

    // iOS never fires the event, so offer the manual route after a moment —
    // long enough not to interrupt the first paint.
    let timer;
    if (isIOS()) {
      timer = setTimeout(() => {
        setIosHelp(true);
        setShow(true);
      }, 2500);
    }

    const onInstalled = () => {
      setShow(false);
      setDeferred(null);
    };
    window.addEventListener("appinstalled", onInstalled);

    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstall);
      window.removeEventListener("appinstalled", onInstalled);
      clearTimeout(timer);
    };
  }, []);

  const dismiss = useCallback(() => {
    setShow(false);
    try {
      localStorage.setItem(DISMISSED_KEY, String(Date.now()));
    } catch {
      /* ignore */
    }
  }, []);

  const install = useCallback(async () => {
    if (!deferred) return;
    deferred.prompt();
    const { outcome } = await deferred.userChoice;
    setDeferred(null);
    setShow(false);
    if (outcome === "dismissed") {
      try {
        localStorage.setItem(DISMISSED_KEY, String(Date.now()));
      } catch {
        /* ignore */
      }
    }
  }, [deferred]);

  if (!show) return null;

  return (
    <div className="install-card" role="dialog" aria-label="تثبيت تطبيق مدار">
      <span className="install-icon">
        <Download size={20} />
      </span>
      <div className="install-main">
        <strong>ثبّت مدار على جهازك</strong>
        {iosHelp ? (
          <p>
            من قائمة المشاركة <Share size={13} className="inline-ico" /> اختر «إضافة إلى الشاشة
            الرئيسية» <Plus size={13} className="inline-ico" />.
          </p>
        ) : (
          <p>افتح مدار مباشرة من شاشتك، بدون متصفح وبسرعة أكبر.</p>
        )}
      </div>
      <div className="install-actions">
        {!iosHelp && (
          <button type="button" className="install-btn" onClick={install}>
            تثبيت
          </button>
        )}
        <button type="button" className="install-close" aria-label="إغلاق" onClick={dismiss}>
          <X size={16} />
        </button>
      </div>
    </div>
  );
}

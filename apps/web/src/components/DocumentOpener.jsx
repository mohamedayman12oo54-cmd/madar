import { useEffect, useRef, useState } from "react";
import { FileText, ExternalLink } from "lucide-react";
import { Banner, Btn } from "../auth/ui.jsx";
import { BASE_URL, ApiError } from "../lib/api.js";

/** Opens a protected PDF. The server hands out a short-lived signed ticket for ONE file; the PDF
 *  opens in a new tab through a plain link (no popup scripting). The ticket is never stored: asking
 *  again simply asks the server again, which re-checks that the viewer may still read the file. */
export default function DocumentOpener({ getTicket, label = "عرض الملف", primary = true }) {
  const [url, setUrl] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const link = useRef(null);

  useEffect(() => {
    // the ticket lives for a couple of minutes; after that the link is withdrawn rather than left dead
    if (!url) return undefined;
    const t = setTimeout(() => setUrl(null), 100000);
    return () => clearTimeout(t);
  }, [url]);

  useEffect(() => {
    if (url) link.current?.click();
  }, [url]);

  const ask = async () => {
    setBusy(true);
    setErr(null);
    try {
      const { ticket } = await getTicket();
      setUrl(`${BASE_URL}/content/document/?${new URLSearchParams({ t: ticket })}`);
    } catch (e) {
      setErr(e instanceof ApiError && e.status !== 404 ? e.message : "هذا الملف غير متاح.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="doc-open">
      <Btn
        type="button"
        variant={primary ? undefined : "ghost"}
        onClick={ask}
        loading={busy}
        loadingText="جارٍ التجهيز…"
      >
        <FileText size={15} /> {label}
      </Btn>
      {url && (
        <a ref={link} className="mini-btn is-primary" href={url} target="_blank" rel="noopener noreferrer">
          <ExternalLink size={13} /> الملف جاهز — اضغط إن لم يُفتح تلقائيًا
        </a>
      )}
      {err && <Banner tone="err">{err}</Banner>}
    </div>
  );
}

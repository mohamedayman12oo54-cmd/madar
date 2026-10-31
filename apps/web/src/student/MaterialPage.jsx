import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowRight, ZoomIn } from "lucide-react";
import { Banner } from "../auth/ui.jsx";
import { studentApi } from "../lib/studentApi.js";
import { ApiError } from "../lib/api.js";
import { PageHeader } from "../dashboard/common.jsx";
import { fmtDate } from "../lib/dates.js";
import SummaryText from "../components/SummaryText.jsx";

/** One summary, read in the app. The text is rendered as plain text blocks (no HTML parsing). */
export default function MaterialPage() {
  const { id } = useParams();
  const [item, setItem] = useState(null);
  const [err, setErr] = useState(null);
  const [big, setBig] = useState(false);

  useEffect(() => {
    setItem(null);
    setErr(null);
    studentApi
      .material(id)
      .then(setItem)
      .catch((e) =>
        setErr(e instanceof ApiError && e.status !== 404 ? e.message : "هذا المحتوى غير متاح لك.")
      );
  }, [id]);

  const back = (
    <Link to="/learn/videos" className="mini-btn">
      <ArrowRight size={13} /> كل المحتوى
    </Link>
  );

  return (
    <>
      <PageHeader infoKey="student_videos" title={item?.title || "الملخص"}>
        {back}
      </PageHeader>
      {err && <Banner tone="err">{err}</Banner>}
      {!item && !err && <p className="field-msg">جاري التحميل...</p>}
      {item && (
        <article className={"summary-reader" + (big ? " is-big" : "")}>
          <div className="summary-meta">
            <span>{item.published_at ? `نُشر في ${fmtDate(item.published_at)}` : "ملخص"}</span>
            <button type="button" className="mini-btn" aria-pressed={big} onClick={() => setBig((b) => !b)}>
              <ZoomIn size={13} /> {big ? "تصغير الخط" : "تكبير الخط"}
            </button>
          </div>
          {item.description && <p className="summary-lead">{item.description}</p>}
          <SummaryText text={item.body || ""} />
        </article>
      )}
    </>
  );
}

import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowRight, ChevronDown, FileQuestion, MessagesSquare } from "lucide-react";
import { Banner, Btn } from "../auth/ui.jsx";
import { studentApi } from "../lib/studentApi.js";
import { ApiError } from "../lib/api.js";
import { PageHeader } from "../dashboard/common.jsx";
import VideoPlayer from "../components/VideoPlayer.jsx";
import { useQuiz } from "./useQuiz.js";

/** Video page.
 *  Desktop: the player takes 3/4 of the width, the description the other 1/4,
 *  and the actions sit underneath.
 *  Phone (YouTube-style): full-bleed player pinned under the top bar, then the
 *  title, a row of action chips, and a collapsible description card. */
export default function VideoDetailPage() {
  const { id } = useParams();
  const [item, setItem] = useState(null);
  const [err, setErr] = useState(null);
  const { quiz, busyId, notice, cancel } = useQuiz();
  const [more, setMore] = useState(false);

  useEffect(() => {
    setItem(null); setErr(null); setMore(false);
    studentApi.video(id).then(setItem).catch((e) => setErr(e instanceof ApiError && e.status !== 404 ? e.message : "هذا الفيديو غير متاح لك."));
    return cancel;
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  const saveProgress = useCallback((position, duration) => {
    studentApi.videoProgress(id, position, duration).catch(() => {});
  }, [id]);

  const back = <Link to="/learn/videos" className="mini-btn"><ArrowRight size={13} /> كل الفيديوهات</Link>;
  if (err) return <><PageHeader infoKey="student_videos" title="الفيديو">{back}</PageHeader><Banner tone="err">{err}</Banner></>;
  if (!item) return <><PageHeader infoKey="student_videos" title="الفيديو">{back}</PageHeader><p className="field-msg">جاري التحميل...</p></>;

  const uploaded = item.source === "upload";
  const url = item.video?.embed_url;
  const safe = typeof url === "string" && url.startsWith("https://");

  const desc = item.description || "";
  const longDesc = desc.length > 90 || desc.includes("\n");

  return (
    <div className="vd">
      <div className="vd-head"><PageHeader infoKey="student_videos" title={item.title}>{back}</PageHeader></div>
      {notice && <Banner tone={notice.tone}>{notice.text}</Banner>}
      <div className="video-detail">
        <div className="video-detail-player">
          {uploaded ? (
            <VideoPlayer itemId={item.id} ticketFor={studentApi.playbackTicket} onProgress={saveProgress}
              startAt={item.progress?.position_seconds || 0} />
          ) : safe ? (
            <iframe className="video-frame" title={item.title} src={url} sandbox="allow-scripts allow-same-origin allow-presentation"
              allow="fullscreen" allowFullScreen referrerPolicy="no-referrer" loading="lazy" />
          ) : <Banner tone="err">تعذّر عرض الفيديو.</Banner>}
        </div>

        {/* Phones only (hidden on desktop, where the title lives in the page header). */}
        <h1 className="vd-title">{item.title}</h1>

        <div className="video-detail-actions">
          <div className="vd-chips">
            <Btn variant="ghost" disabled={!item.can_quiz} loading={busyId === item.id} loadingText="جارٍ إعداد الاختبار…" onClick={() => quiz(item)}>
              <FileQuestion size={15} /> اختبرني في هذا الدرس
            </Btn>
            <Link to="/learn/assistant" className="mini-btn"><MessagesSquare size={14} /> اسأل المساعد الدراسي</Link>
          </div>
          {!item.can_quiz && <span className="stat-sub">لم يضف المعلّم ملخصًا كافيًا لتوليد اختبار بعد.</span>}
        </div>

        <aside className={"video-detail-info" + (more ? " is-open" : "")}>
          <h3>الوصف</h3>
          <p>{desc || "لا يوجد وصف لهذا الفيديو."}</p>
          {longDesc && (
            <button type="button" className="vd-more" aria-expanded={more} onClick={() => setMore((v) => !v)}>
              {more ? "عرض أقل" : "المزيد"} <ChevronDown size={14} />
            </button>
          )}
        </aside>
      </div>
    </div>
  );
}

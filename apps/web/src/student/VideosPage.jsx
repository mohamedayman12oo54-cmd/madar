import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Play, FileQuestion } from "lucide-react";
import { Banner, Btn, Modal } from "../auth/ui.jsx";
import { studentApi } from "../lib/studentApi.js";
import { pollUntilDone } from "../lib/poll.js";
import { ApiError } from "../lib/api.js";
import { PageHeader, Empty } from "../dashboard/common.jsx";
import VideoPlayer from "../components/VideoPlayer.jsx";

const newKey = () => globalThis.crypto?.randomUUID?.() ?? `k-${Date.now()}-${Math.random().toString(16).slice(2)}`;

function Watch({ item, onClose }) {
  // Uploaded videos stream from Madar through a signed, short-lived ticket.
  // Externally hosted ones keep the sandboxed embed.
  const uploaded = item.source === "upload";
  const url = item.video?.embed_url;
  const safe = typeof url === "string" && url.startsWith("https://");

  const saveProgress = useCallback((position, duration) => {
    studentApi.videoProgress(item.id, position, duration).catch(() => {});
  }, [item.id]);

  return (
    <Modal size="md" title={item.title} text={item.description} onClose={onClose}>
      {uploaded ? (
        <VideoPlayer
          itemId={item.id}
          ticketFor={studentApi.playbackTicket}
          onProgress={saveProgress}
          startAt={item.progress?.position_seconds || 0}
        />
      ) : safe ? (
        <iframe className="video-frame" title={item.title} src={url} sandbox="allow-scripts allow-same-origin allow-presentation"
          allow="fullscreen" allowFullScreen referrerPolicy="no-referrer" loading="lazy" />
      ) : <Banner tone="err">تعذّر عرض الفيديو.</Banner>}
    </Modal>
  );
}

export default function VideosPage() {
  const nav = useNavigate();
  const [items, setItems] = useState(null);
  const [err, setErr] = useState(null);
  const [watch, setWatch] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [notice, setNotice] = useState(null);
  const keys = useRef({});          // one idempotency key per video per attempt: a double tap never makes two quizzes
  const abort = useRef(null);

  useEffect(() => { studentApi.videos().then((d) => setItems(d.results)).catch((e) => setErr(e instanceof ApiError ? e.message : "تعذّر تحميل الفيديوهات.")); return () => abort.current?.abort(); }, []);

  const quiz = async (item) => {
    setBusyId(item.id); setNotice(null);
    keys.current[item.id] ||= newKey();
    const controller = new AbortController(); abort.current = controller;
    try {
      const op = await studentApi.quizzes.request(item.id, keys.current[item.id]);
      const out = await pollUntilDone(() => studentApi.quizzes.operation(op.id), { isDone: (o) => o.status === "completed" || o.status === "failed", signal: controller.signal });
      if (out.status === "done" && out.op.status === "completed" && out.op.quiz_id) { delete keys.current[item.id]; nav(`/learn/quizzes/${out.op.quiz_id}`); return; }
      delete keys.current[item.id]; // finished (or failed): a deliberate retry is a NEW request
      setNotice({ tone: "err", text: out.status === "timeout" ? "استغرق إعداد الاختبار وقتًا أطول من المتوقع. حاول لاحقًا." : (out.op?.error || "تعذّر إعداد الاختبار. حاول مرة أخرى.") });
    } catch (e) {
      setNotice({ tone: "err", text: e instanceof ApiError ? e.message : "تعذّر طلب الاختبار." });
    } finally { setBusyId(null); }
  };

  return (
    <>
      <PageHeader infoKey="student_videos" title="الفيديوهات" />
      {notice && <Banner tone={notice.tone}>{notice.text}</Banner>}
      {err && <Banner tone="err">{err}</Banner>}
      {!items && !err && <p className="field-msg">جاري التحميل...</p>}
      {items && items.length === 0 && <Empty title="لا توجد فيديوهات بعد" text="ستظهر هنا الفيديوهات التي ينشرها معلمك لك." />}
      <div className="list-rows">{items?.map((v) => (
        <div key={v.id} className="list-row">
          <div><strong>{v.title}</strong>{v.description && <div className="stat-sub">{v.description.slice(0, 90)}{v.description.length > 90 ? "…" : ""}</div>}</div>
          <div className="row-actions">
            {v.video && <button className="mini-btn" onClick={() => setWatch(v)}><Play size={13} /> مشاهدة</button>}
            {v.can_quiz && <Btn variant="ghost" loading={busyId === v.id} loadingText="جارٍ إعداد الاختبار…" onClick={() => quiz(v)}><FileQuestion size={15} /> اختبرني</Btn>}
          </div>
        </div>))}</div>
      {watch && <Watch item={watch} onClose={() => setWatch(null)} />}
    </>
  );
}

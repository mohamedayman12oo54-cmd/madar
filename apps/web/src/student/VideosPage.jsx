import { useEffect, useState } from "react";
import { ClipboardCheck, FileText, NotebookPen, Play } from "lucide-react";
import { Banner } from "../auth/ui.jsx";
import { studentApi } from "../lib/studentApi.js";
import { ApiError } from "../lib/api.js";
import { PageHeader, Empty } from "../dashboard/common.jsx";
import VideoCard from "./VideoCard.jsx";
import MaterialCard from "./MaterialCard.jsx";
import { ExamList } from "./ExamPages.jsx";

// The student's educational content, split into the same sections the teacher publishes into.
const TABS = {
  video: {
    label: "فيديوهات",
    icon: Play,
    emptyTitle: "لا توجد فيديوهات بعد",
    emptyText: "ستظهر هنا الفيديوهات التي ينشرها معلمك لك.",
  },
  pdf: {
    label: "ملفات PDF",
    icon: FileText,
    emptyTitle: "لا توجد ملفات بعد",
    emptyText: "ستظهر هنا الملفات التي ينشرها معلمك لك.",
  },
  summary: {
    label: "ملخصات وملاحظات",
    icon: NotebookPen,
    emptyTitle: "لا توجد ملخصات بعد",
    emptyText: "ستظهر هنا الملخصات والملاحظات التي ينشرها معلمك لك.",
  },
  // exams have their own list (ExamPages.ExamList): this entry only adds the tab
  exam: { label: "امتحانات", icon: ClipboardCheck },
};

export default function VideosPage() {
  const [tab, setTab] = useState("video");
  const [items, setItems] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let alive = true;
    setItems(null);
    setErr(null);
    if (tab === "exam") return undefined;
    const req = tab === "video" ? studentApi.videos() : studentApi.materials(tab);
    req
      .then((d) => alive && setItems(d.results))
      .catch((e) => alive && setErr(e instanceof ApiError ? e.message : "تعذّر تحميل المحتوى."));
    return () => {
      alive = false;
    };
  }, [tab]);

  return (
    <>
      <PageHeader infoKey="student_videos" title="المحتوى التعليمي" />
      <div className="dash-tabs tabs-icons" role="tablist" aria-label="أقسام المحتوى">
        {Object.entries(TABS).map(([k, v]) => (
          <button
            key={k}
            type="button"
            role="tab"
            aria-selected={tab === k}
            className={"dash-tab" + (tab === k ? " active" : "")}
            onClick={() => setTab(k)}
          >
            <v.icon size={15} aria-hidden="true" /> {v.label}
          </button>
        ))}
      </div>
      {tab === "exam" && <ExamList />}
      {tab !== "exam" && err && <Banner tone="err">{err}</Banner>}
      {tab !== "exam" && !items && !err && <p className="field-msg">جاري التحميل...</p>}
      {items && items.length === 0 && (
        <Empty title={TABS[tab].emptyTitle} text={TABS[tab].emptyText} />
      )}
      <div className="list-rows">
        {items?.map((v) =>
          tab === "video" ? (
            <VideoCard key={v.id} video={v} />
          ) : (
            <MaterialCard key={v.id} item={v} />
          )
        )}
      </div>
    </>
  );
}

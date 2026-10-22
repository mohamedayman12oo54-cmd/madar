import { useEffect, useState } from "react";
import { Banner } from "../auth/ui.jsx";
import { studentApi } from "../lib/studentApi.js";
import { ApiError } from "../lib/api.js";
import { PageHeader, Empty } from "../dashboard/common.jsx";
import VideoCard from "./VideoCard.jsx";

export default function VideosPage() {
  const [items, setItems] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    studentApi
      .videos()
      .then((d) => setItems(d.results))
      .catch((e) => setErr(e instanceof ApiError ? e.message : "تعذّر تحميل الفيديوهات."));
  }, []);

  return (
    <>
      <PageHeader infoKey="student_videos" title="الفيديوهات" />
      {err && <Banner tone="err">{err}</Banner>}
      {!items && !err && <p className="field-msg">جاري التحميل...</p>}
      {items && items.length === 0 && (
        <Empty title="لا توجد فيديوهات بعد" text="ستظهر هنا الفيديوهات التي ينشرها معلمك لك." />
      )}
      <div className="list-rows">
        {items?.map((v) => (
          <VideoCard key={v.id} video={v} />
        ))}
      </div>
    </>
  );
}

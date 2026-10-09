import { useEffect, useState } from "react";
import { Banner } from "../auth/ui.jsx";
import { studentApi } from "../lib/studentApi.js";
import { ApiError } from "../lib/api.js";
import { PageHeader, Empty } from "../dashboard/common.jsx";
import { STATE_LABEL, STATE_TONE, Stars } from "./HomePage.jsx";

const TABS = [["attendance", "الحضور"], ["recitation", "التسميع"], ["payments", "الدفع"], ["evaluation", "التقييم"]];
const LABEL = { present: "حاضر", absent: "غائب", studied: "ذاكر", not_studied: "لم يذاكر" };
const TONE = { present: "good", studied: "good", absent: "bad", not_studied: "bad" };
const fmtDate = (iso) => new Date(iso).toLocaleDateString("ar-EG", { dateStyle: "medium" });

export default function RecordsPage() {
  const [tab, setTab] = useState("attendance");
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    setData(null); setErr(null);
    studentApi[tab]().then(setData).catch((e) => setErr(e instanceof ApiError ? e.message : "تعذّر تحميل السجل."));
  }, [tab]);

  return (
    <>
      <PageHeader infoKey="student_records" title="سجلّي">
        <div className="seg" role="tablist">{TABS.map(([k, l]) => <button key={k} className={tab === k ? "active" : ""} onClick={() => setTab(k)}>{l}</button>)}</div>
      </PageHeader>
      {err && <Banner tone="err">{err}</Banner>}
      {!data && !err && <p className="field-msg">جاري التحميل...</p>}
      {data && (tab === "attendance" || tab === "recitation") && (
        <>
          <div className="tag-list" style={{ marginBlockEnd: 12 }}>
            {Object.entries(data.summary).map(([k, n]) => <span key={k} className={"chip-s " + TONE[k]}>{LABEL[k]}: {n}</span>)}
          </div>
          {data.results.length === 0 ? <Empty title="لا توجد سجلات بعد" text="ستظهر هنا بعد أن يسجّلها معلمك في الحصص." /> : (
            <div className="list-rows">{data.results.map((r) => (
              <div key={r.id} className="list-row"><div><strong>{r.group}</strong><div className="stat-sub">{fmtDate(r.date)}</div></div>
                <span className={"chip-s " + TONE[r.status]}>{LABEL[r.status]}</span></div>))}</div>)}
        </>
      )}
      {data && tab === "payments" && (
        <div className="list-rows">{data.results.map((r) => (
          <div key={r.month} className="list-row"><strong>{r.month}</strong><span className={"chip-s " + (r.status === "paid" ? "good" : "bad")}>{r.status === "paid" ? "مدفوع" : "غير مدفوع"}</span></div>))}</div>
      )}
      {data && tab === "evaluation" && (data.results.length === 0
        ? <Empty title="لا يوجد تقييم بعد" text="يظهر تقييمك الشهري هنا بعد أن ينشره معلمك." />
        : <div className="list-rows">{data.results.map((r) => (
          <div key={r.month} className="list-row"><strong>{r.month}</strong>
            <span className="row-actions">{r.state && <span className={"chip-s " + STATE_TONE[r.state]}>{STATE_LABEL[r.state]}</span>}{r.rating ? <Stars value={r.rating} /> : <span className="stat-sub">التقييم لم يُنشر</span>}</span></div>))}</div>)}
    </>
  );
}

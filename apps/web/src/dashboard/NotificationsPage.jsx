import { useEffect, useState } from "react";
import { RefreshCw, Send } from "lucide-react";
import { Field, TextInput, Btn, Banner } from "../auth/ui.jsx";
import { notificationsApi } from "../lib/dashboardApi.js";
import { ApiError } from "../lib/api.js";
import { useGrades } from "./useGrades.js";
import { useGroups } from "./useGroups.js";
import { CheckList, Empty, PageHeader, fmtDateTime, toggleId } from "./common.jsx";

const DELIVERY = { pending: ["قيد الإرسال", "warn"], sent: ["تم", "good"], failed: ["فشل", "bad"] };
const listOf = (d) => (Array.isArray(d) ? d : d?.results || []);

function Compose({ onSent }) {
  const { grades } = useGrades();
  const { groups } = useGroups();
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [gradeIds, setGradeIds] = useState([]);
  const [groupIds, setGroupIds] = useState([]);
  const [err, setErr] = useState(null);
  const [fe, setFe] = useState({});
  const [saving, setSaving] = useState(false);
  const submit = async (e) => {
    e.preventDefault(); setErr(null); setFe({});
    if (title.trim().length < 2) { setFe({ title: "أدخل عنوانًا للرسالة." }); return; }
    if (!gradeIds.length && !groupIds.length) { setErr("اختر صفًا أو مجموعة واحدة على الأقل."); return; }
    setSaving(true);
    try { const r = await notificationsApi.broadcast({ title: title.trim(), body: body.trim(), grade_ids: gradeIds, group_ids: groupIds }); setTitle(""); setBody(""); setGradeIds([]); setGroupIds([]); onSent(r.recipients); }
    catch (e2) { if (e2 instanceof ApiError && e2.fields) setFe(e2.fields); else setErr(e2 instanceof ApiError ? e2.message : "تعذّر الإرسال."); }
    finally { setSaving(false); }
  };
  return (
    <form onSubmit={submit} className="dash-form dash-card" noValidate>
      <h3>رسالة جماعية</h3>
      {err && <Banner tone="err">{err}</Banner>}
      <Field label="العنوان" required error={fe.title}><TextInput value={title} onChange={(e) => setTitle(e.target.value)} maxLength={150} /></Field>
      <Field label="نص الرسالة (اختياري)" error={fe.body}><textarea className="inp" rows={3} maxLength={500} value={body} onChange={(e) => setBody(e.target.value)} /></Field>
      <Field label="الصفوف"><CheckList items={grades} selected={gradeIds} onToggle={(id) => setGradeIds((l) => toggleId(l, id))} empty="لا توجد صفوف." /></Field>
      <Field label="المجموعات"><CheckList items={groups} selected={groupIds} onToggle={(id) => setGroupIds((l) => toggleId(l, id))} empty="لا توجد مجموعات." /></Field>
      <p className="stat-sub">تصل الرسالة للطلاب النشطين فقط، مرة واحدة لكل طالب، داخل التطبيق وبالإشعار الفوري. لا يمكن سحبها بعد الإرسال.</p>
      <Btn type="submit" loading={saving} loadingText="جارٍ الإرسال…"><Send size={15} /> إرسال</Btn>
    </form>
  );
}

export default function NotificationsPage() {
  const [tab, setTab] = useState("log");
  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState({ results: [] });
  const [summary, setSummary] = useState(null);
  const [status, setStatus] = useState("loading");
  const [notice, setNotice] = useState(null);

  useEffect(() => { setPage(1); }, [typeFilter, statusFilter]);
  const load = () => {
    notificationsApi.summary().then(setSummary).catch(() => {});
    return notificationsApi.list({ type: typeFilter, delivery_status: statusFilter, page })
      .then((d) => { setData(Array.isArray(d) ? { results: d } : d); setStatus("ready"); }).catch(() => setStatus("error"));
  };
  useEffect(() => { load(); }, [typeFilter, statusFilter, page]); // eslint-disable-line react-hooks/exhaustive-deps

  const retry = async () => {
    try { const r = await notificationsApi.retryFailed(); setNotice({ tone: "info", text: `أُعيد ${r.requeued} إشعار إلى قائمة الإرسال.` }); load(); }
    catch (e) { setNotice({ tone: "err", text: e instanceof ApiError ? e.message : "تعذّر تنفيذ الإجراء." }); }
  };

  return (
    <>
      <PageHeader infoKey="notifications" title="الإشعارات">
        <div className="seg"><button className={tab === "log" ? "active" : ""} onClick={() => setTab("log")}>السجل</button>
          <button className={tab === "send" ? "active" : ""} onClick={() => setTab("send")}>رسالة جماعية</button></div>
      </PageHeader>
      {notice && <Banner tone={notice.tone}>{notice.text}</Banner>}
      {tab === "send" ? <Compose onSent={(n) => { setTab("log"); setNotice({ tone: "info", text: `أُرسلت الرسالة إلى ${n} طالب.` }); load(); }} /> : (
        <>
          {summary && <div className="dash-cards">
            <div className="dash-card"><div className="k">قيد الإرسال</div><div className="v">{summary.pending}</div></div>
            <div className="dash-card"><div className="k">تم الإرسال</div><div className="v">{summary.sent}</div></div>
            <div className="dash-card"><div className="k">فشل الإرسال</div><div className="v">{summary.failed}</div>
              {summary.failed > 0 && <button className="mini-btn" style={{ marginBlockStart: 8 }} onClick={retry}><RefreshCw size={13} /> إعادة المحاولة</button>}</div></div>}
          <div className="dash-filters">
            <select className="inp" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}><option value="">كل الأنواع</option>
              <option value="absent">غياب</option><option value="not_studied">لم يذاكر</option><option value="new_video">فيديو جديد</option>
              <option value="rating_published">نشر التقييم</option><option value="broadcast">رسالة جماعية</option></select>
            <select className="inp" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}><option value="">كل الحالات</option>
              <option value="pending">قيد الإرسال</option><option value="sent">تم</option><option value="failed">فشل</option></select>
          </div>
          {status === "loading" && <p className="field-msg">جاري التحميل...</p>}
          {status === "error" && <Banner tone="err">تعذّر تحميل الإشعارات.</Banner>}
          {status === "ready" && listOf(data).length === 0 && <Empty title="لا توجد إشعارات" text="ستظهر هنا إشعارات الغياب وعدم المذاكرة والفيديوهات والتقييمات والرسائل الجماعية." />}
          <div className="list-rows">{listOf(data).map((n) => (
            <div key={n.id} className="list-row">
              <div><strong>{n.type_label}</strong> — {n.student.name || "—"}<div className="stat-sub">{n.title}{n.body ? ` — ${n.body}` : ""} • {fmtDateTime(n.created_at)}</div></div>
              <span className={"chip-s " + DELIVERY[n.delivery_status][1]}>{DELIVERY[n.delivery_status][0]}</span></div>))}</div>
          {(data.previous || data.next) && <div className="dash-pager"><button disabled={!data.previous} onClick={() => setPage((p) => p - 1)}>السابق</button><span>صفحة {page}</span><button disabled={!data.next} onClick={() => setPage((p) => p + 1)}>التالي</button></div>}
        </>)}
    </>
  );
}

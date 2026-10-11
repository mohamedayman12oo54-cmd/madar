import { useEffect, useId, useState } from "react";
import { Plus, Play, Pencil, Trash2, Send, X } from "lucide-react";
import { Field, TextInput, Btn, Banner, Modal } from "../auth/ui.jsx";
import { enrollmentsApi } from "../lib/academicsApi.js";
import { contentApi } from "../lib/dashboardApi.js";
import { extractVideoId } from "../lib/video.js";
import { ApiError } from "../lib/api.js";
import { useGrades } from "./useGrades.js";
import { useGroups } from "./useGroups.js";
import { CheckList, Confirm, Empty, PageHeader, toggleId, useDebounced } from "./common.jsx";
import { UploadCloud, FileVideo, AlertCircle } from "lucide-react";

const listOf = (d) => (Array.isArray(d) ? d : d?.results || []);

function VideoModal({ item, onClose }) {
  const url = item.video?.embed_url;
  const safe = typeof url === "string" && url.startsWith("https://"); // defence in depth: the server only builds https embeds
  return (
    <Modal size="md" title={item.title} text={item.description} onClose={onClose}>
      {safe ? <iframe className="video-frame" title={item.title} src={url} sandbox="allow-scripts allow-same-origin allow-presentation"
        allow="fullscreen" allowFullScreen referrerPolicy="no-referrer" loading="lazy" /> : <Banner tone="err">تعذّر عرض الفيديو.</Banner>}
    </Modal>
  );
}

function ItemFormModal({ item, grades, groups, onClose, onSaved }) {
  // The file needs something to attach to, but making the teacher save first
  // and come back is a pointless round trip. On the first file pick we create
  // the content as a draft with whatever title has been typed, then keep
  // editing it — so uploading and filling the form happen together.
  const [draft, setDraft] = useState(item || null);

  const ensureItem = async () => {
    if (draft) return draft;
    const created = await contentApi.create({
      title: (title || "").trim() || "فيديو بلا عنوان",
      description, quiz_source: quizSource,
      video_provider: "none", video_ref: "",
      grade_ids: [], group_ids: [], enrollment_ids: [],
    });
    setDraft(created);
    return created;
  };

  const onUploaded = onSaved;
  const formId = useId();
  const editing = !!item;
  const [title, setTitle] = useState(item?.title || "");
  const [description, setDescription] = useState(item?.description || "");
  const [quizSource, setQuizSource] = useState(item?.quiz_source || "");
  // New content always uploads; an older item keeps showing its external
  // source until the teacher replaces it with a file.
  const [provider, setProvider] = useState(
    item?.source === "external" && item?.video?.provider ? item.video.provider : "upload");
  const [ref, setRef] = useState("");
  const [gradeIds, setGradeIds] = useState(item?.targets.grades.map((g) => g.id) || []);
  const [groupIds, setGroupIds] = useState(item?.targets.groups.map((g) => g.id) || []);
  const [students, setStudents] = useState(item?.targets.students || []);
  const [studentSearch, setStudentSearch] = useState("");
  const q = useDebounced(studentSearch);
  const [found, setFound] = useState([]);
  const [err, setErr] = useState(null);
  const [fe, setFe] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (q.trim().length < 2) { setFound([]); return; }
    enrollmentsApi.list({ search: q, is_active: "true" }).then((d) => setFound(listOf(d).slice(0, 6))).catch(() => setFound([]));
  }, [q]);

  const submit = async (e) => {
    e.preventDefault(); setErr(null);
    if (!title.trim()) { setFe({ title: "أدخل عنوان المحتوى." }); return; }
    const body = { title: title.trim(), description: description.trim(), quiz_source: quizSource.trim(), grade_ids: gradeIds, group_ids: groupIds, enrollment_ids: students.map((s) => s.id) };
    if (provider === "none") { body.video_provider = "none"; body.video_ref = ""; }
    else if (provider === "upload") { body.video_provider = "none"; body.video_ref = ""; }
    else if (ref.trim() || !editing || provider !== item.video?.provider) {
      const id = extractVideoId(provider, ref);
      if (!id) { setFe({ video_ref: provider === "youtube" ? "الصق رابط فيديو يوتيوب صحيحًا." : "الصق رابط فيديو Vimeo صحيحًا." }); return; }
      body.video_provider = provider; body.video_ref = id;
    }
    setFe({}); setSaving(true);
    try { draft ? await contentApi.update(draft.id, body) : await contentApi.create(body); onSaved(); }
    catch (e2) { if (e2 instanceof ApiError && e2.fields) setFe(e2.fields); else setErr(e2 instanceof ApiError ? e2.message : "تعذّر الحفظ."); }
    finally { setSaving(false); }
  };

  return (
    <Modal size="lg" title={editing ? "تعديل المحتوى" : "إضافة محتوى"}
      text="حدّد من يشاهد هذا الفيديو. الفيديو بلا مستهدفين مسودة لا يراها أحد." onClose={onClose}
      footer={<>
        <Btn variant="ghost" type="button" onClick={onClose}>إلغاء</Btn>
        <Btn type="submit" form={formId} loading={saving} loadingText="جارٍ الحفظ…">{editing ? "حفظ التعديلات" : "إضافة المحتوى"}</Btn>
      </>}>
      <form id={formId} onSubmit={submit} className="dash-form" noValidate>
        {err && <div className="form-wide"><Banner tone="err">{err}</Banner></div>}
        {/* 1 — what the lesson is */}
        <div className="form-wide form-section">
          <h4 className="form-section-title">بيانات المحتوى</h4>
        </div>
        <Field className="form-wide" label="العنوان" required error={fe.title}>
          <TextInput value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} autoFocus
            placeholder="مثال: شرح الدرس الثالث — المتتابعات" /></Field>
        <Field className="form-wide" label="الوصف (اختياري)" hint="سطر أو سطران يظهران للطالب تحت العنوان.">
          <textarea className="inp" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} /></Field>

        {/* 2 — the file itself */}
        <div className="form-wide form-section">
          <h4 className="form-section-title">الفيديو</h4>
        </div>
        <div className="form-wide">
          <VideoUploadField item={draft} ensureItem={ensureItem} onUploaded={onUploaded} />
        </div>

        {/* 3 — optional AI material */}
        <Field className="form-wide" label="ملخص الدرس لتوليد الاختبارات (اختياري)"
          hint="يُستخدم فقط لتوليد اختبارات بالذكاء الاصطناعي ولا يظهر للطالب. الفيديو نفسه لا يُقرأ.">
          <textarea className="inp" rows={4} maxLength={4000} value={quizSource} onChange={(e) => setQuizSource(e.target.value)} /></Field>

        {/* 4 — who receives it */}
        <div className="form-wide form-section">
          <h4 className="form-section-title">من يشاهد الفيديو</h4>
          <p className="field-msg">اختر الصف ثم المجموعة. الفيديو بلا مستهدفين يبقى مسودة لا يراها أحد.</p>
        </div>
        <Field className="form-wide" label="الصفوف المستهدفة" error={fe.grade_ids}><CheckList items={grades} selected={gradeIds} onToggle={(id) => setGradeIds((l) => toggleId(l, id))} /></Field>
        <Field className="form-wide" label="المجموعات المستهدفة" error={fe.group_ids}><CheckList items={groups} selected={groupIds} onToggle={(id) => setGroupIds((l) => toggleId(l, id))} /></Field>
        <Field className="form-wide" label="طلاب بعينهم (اختياري)" error={fe.enrollment_ids}>
          <TextInput value={studentSearch} onChange={(e) => setStudentSearch(e.target.value)} placeholder="ابحث باسم الطالب أو رقمه…" />
          {found.length > 0 && <div className="tag-list" style={{ marginBlockStart: 8 }}>{found.filter((f) => !students.some((s) => s.id === f.id)).map((f) => (
            <button type="button" key={f.id} className="mini-btn" onClick={() => { setStudents((l) => [...l, { id: f.id, name: f.student.name }]); setStudentSearch(""); setFound([]); }}>+ {f.student.name}</button>))}</div>}
          {students.length > 0 && <div className="tag-list" style={{ marginBlockStart: 8 }}>{students.map((s) => (
            <span key={s.id} className="chip-s">{s.name} <button type="button" aria-label="إزالة" onClick={() => setStudents((l) => l.filter((x) => x.id !== s.id))}><X size={11} /></button></span>))}</div>}
        </Field>
      </form>
    </Modal>
  );
}

export default function ContentPage() {
  const { grades } = useGrades();
  const { groups } = useGroups();
  const [data, setData] = useState(null);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState(null);
  const [form, setForm] = useState(null);
  const [view, setView] = useState(null);
  const [del, setDel] = useState(null);
  const [pub, setPub] = useState(null);
  const [notice, setNotice] = useState(null);
  const [filter, setFilter] = useState("");

  const load = () => contentApi.list({ published: filter })
    .then((d) => { setData(listOf(d)); setStatus("ready"); })
    .catch((e) => { setError(e instanceof ApiError ? e.message : "تعذّر تحميل المحتوى."); setStatus("error"); });
  useEffect(() => { load(); }, [filter]); // eslint-disable-line react-hooks/exhaustive-deps
  const total = (t) => t.grades.length + t.groups.length + t.students.length;

  return (
    <>
      <PageHeader infoKey="content" title="المحتوى التعليمي">
        <Btn onClick={() => setForm("add")}><Plus size={16} /> إضافة محتوى</Btn>
      </PageHeader>
      {notice && <Banner tone={notice.tone}>{notice.text}</Banner>}
      <div className="dash-filters"><select className="inp" value={filter} onChange={(e) => setFilter(e.target.value)}>
        <option value="">الكل</option><option value="1">المنشور</option><option value="0">المسودات</option></select></div>
      {status === "loading" && <p className="field-msg">جاري تحميل المحتوى...</p>}
      {status === "error" && <Banner tone="err">{error}</Banner>}
      {status === "ready" && data.length === 0 && <Empty title="لا يوجد محتوى بعد" text="أضف أول فيديو، ثم حدّد من يشاهده وانشره." />}
      <div className="list-rows">
        {data?.map((it) => (
          <div key={it.id} className="list-row">
            <div><strong>{it.title}</strong> <span className={"chip-s " + (it.published ? "good" : "warn")}>{it.published ? "منشور" : "مسودة"}</span>
              <div className="stat-sub">
                {total(it.targets) === 0 ? "بلا مستهدفين" : [
                  ...it.targets.grades.map((g) => `صف: ${g.name}`), ...it.targets.groups.map((g) => `مجموعة: ${g.name}`),
                  it.targets.students.length ? `${it.targets.students.length} طالب` : null].filter(Boolean).join(" • ")}</div></div>
            {!it.published && (
              /* A draft is invisible to students. Say exactly what is still
                 missing — a small "مسودة" chip was not enough, and teachers
                 were uploading then wondering why nothing reached anyone. */
              <div className="draft-hint">
                <AlertCircle size={14} />
                <span>{!hasVideo(it)
                  ? "لم يُرفع ملف فيديو بعد — افتح «تعديل» وارفع الملف."
                  : total(it.targets) === 0
                    ? "حدّد الصف أو المجموعة من «تعديل» ثم اضغط «نشر»."
                    : "جاهز للنشر — اضغط «نشر» ليظهر للطلاب."}</span>
              </div>
            )}
            <div className="row-actions">
              {it.video && <button className="mini-btn" onClick={() => setView(it)}><Play size={13} /> معاينة</button>}
              {!it.published && (
                <button className={"mini-btn" + (hasVideo(it) && total(it.targets) > 0 ? " is-primary" : "")}
                  onClick={() => setPub(it)}><Send size={13} /> نشر</button>
              )}
              <button className="mini-btn" onClick={() => setForm(it)}><Pencil size={13} /> تعديل</button>
              <button className="mini-btn danger" onClick={() => setDel(it)}><Trash2 size={13} /></button>
            </div>
          </div>))}
      </div>
      {form && <ItemFormModal item={form === "add" ? null : form} grades={grades} groups={groups} onClose={() => setForm(null)} onSaved={() => { setForm(null); load(); }} />}
      {view && <VideoModal item={view} onClose={() => setView(null)} />}
      {pub && <Confirm title="نشر المحتوى؟" confirmLabel="نشر الآن" text={`سيظهر «${pub.title}» للمستهدفين ويصل الطلاب النشطين إشعار «فيديو جديد» مرة واحدة.`} onClose={() => setPub(null)}
        onConfirm={async () => { try { const r = await contentApi.publish(pub.id); setNotice({ tone: "info", text: `تم النشر وإشعار ${r.notified} طالب.` }); } catch (e) { setNotice({ tone: "err", text: e instanceof ApiError ? e.message : "تعذّر النشر." }); } setPub(null); load(); }} />}
      {del && <Confirm danger title="حذف المحتوى" confirmLabel="حذف" text={`سيُحذف «${del.title}» نهائيًا ولا يمكن التراجع.`} onClose={() => setDel(null)}
        onConfirm={async () => { await contentApi.remove(del.id).catch(() => {}); setDel(null); load(); }} />}
    </>
  );
}

const MB = 1024 * 1024;

/** An item is playable only once a file (or legacy external reference) exists. */
const hasVideo = (it) => it.source === "upload" || Boolean(it.video?.embed_url);

const ACCEPT = "video/mp4,video/webm,video/quicktime,.mp4,.m4v,.webm,.mov";

/** Uploads an actual video file to Madar, with real progress.
 *  Client-side checks are a courtesy only — the server re-validates the
 *  extension, the declared type AND the file's leading bytes. */
function VideoUploadField({ item, ensureItem, onUploaded }) {
  const [pct, setPct] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [err, setErr] = useState(null);
  const [info, setInfo] = useState(
    item?.source === "upload"
      ? { original_filename: item.original_filename, file_size: item.file_size }
      : null);

  const upload = async (file) => {
    if (!file || pct !== null) return;
    setErr(null); setPct(0);
    try {
      // Creates the draft on the fly the first time, so the teacher never has
      // to save-and-reopen just to attach a file.
      const target = item || (ensureItem ? await ensureItem() : null);
      if (!target) throw new Error("تعذّر تجهيز المحتوى للرفع.");
      setInfo(await contentApi.uploadVideo(target.id, file, setPct));
      onUploaded?.();
    } catch (e2) {
      setErr(e2?.data?.video?.[0] || e2?.data?.detail || e2?.message || "تعذّر رفع الملف.");
    } finally {
      setPct(null);
    }
  };

  const pick = (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";               // allow re-picking the same file
    upload(file);
  };

  const drop = async () => {
    if (!item || !window.confirm("حذف ملف الفيديو من هذا المحتوى؟")) return;
    try { await contentApi.removeVideo(item.id); setInfo(null); onUploaded?.(); }
    catch (e2) { setErr(e2?.message || "تعذّر الحذف."); }
  };

  return (
    <div className="upload-field">
      {info?.original_filename && (
        <div className="upload-current">
          <FileVideo size={16} />
          <span className="upload-name">{info.original_filename}</span>
          {info.file_size ? <span className="stat-sub">{(info.file_size / MB).toFixed(1)} م.ب</span> : null}
          <button type="button" className="mini-btn" onClick={drop}>حذف</button>
        </div>
      )}
      <label
        className={"upload-drop" + (dragging ? " is-dragging" : "")}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const file = e.dataTransfer?.files?.[0];
          if (file) upload(file);
        }}>
        <UploadCloud size={22} />
        <span><strong>اسحب الفيديو هنا</strong> أو اضغط للاختيار</span>
        <span className="stat-sub">MP4 · M4V · WEBM · MOV</span>
        <input type="file" accept={ACCEPT} onChange={pick} hidden disabled={pct !== null} />
      </label>
      {pct !== null && (
        <div className="upload-bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
          <div className="upload-bar-fill" style={{ width: `${pct}%` }} />
          <span className="upload-pct">{pct}%</span>
        </div>
      )}
      {err && <Banner tone="err">{err}</Banner>}
    </div>
  );
}

import { useEffect, useState } from "react";
import { BookOpen, Pencil, Play, Plus, Search, Trash2 } from "lucide-react";
import { Field, TextInput, Btn, Banner, Modal } from "../auth/ui.jsx";
import { contentApi } from "../lib/contentApi.js";
import { ApiError } from "../lib/api.js";
import { useGrades } from "./useGrades.js";
import ComingSoon from "./ComingSoon.jsx";

const PROVIDERS = [
  { value: "none", label: "بدون فيديو" },
  { value: "youtube", label: "YouTube" },
  { value: "vimeo", label: "Vimeo" },
];
const REF_HINT = {
  youtube: "المعرّف فقط (11 حرفًا) — وليس الرابط الكامل. مثال: dQw4w9WgXcQ",
  vimeo: "المعرّف الرقمي فقط — وليس الرابط الكامل. مثال: 123456789",
};

function useDebounced(value, delay = 350) {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), delay); return () => clearTimeout(t); }, [value, delay]);
  return v;
}

function ContentFormModal({ item, grades, onClose, onSaved }) {
  const editing = !!item;
  const [title, setTitle] = useState(item?.title || "");
  const [description, setDescription] = useState(item?.description || "");
  const [gradeId, setGradeId] = useState(item?.grade?.id || "");
  const [provider, setProvider] = useState(item?.video?.provider || "none");
  const [ref, setRef] = useState("");   // the raw id is deliberately never sent back by the API
  const [err, setErr] = useState(null);
  const [fe, setFe] = useState({});
  const [saving, setSaving] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setErr(null); setFe({});
    if (!title.trim()) { setFe({ title: "أدخل عنوان المحتوى." }); return; }
    const payload = { title: title.trim(), description, grade_id: gradeId ? Number(gradeId) : null };
    // When editing, only touch the video if the teacher actually changed it.
    const videoTouched = !editing || provider !== (item.video?.provider || "none") || ref.trim() !== "";
    if (videoTouched) { payload.video_provider = provider; payload.video_ref = provider === "none" ? "" : ref.trim(); }
    setSaving(true);
    try {
      if (editing) await contentApi.update(item.id, payload);
      else await contentApi.create(payload);
      onSaved();
    } catch (e2) {
      if (e2 instanceof ApiError && e2.fields) setFe(e2.fields);
      else setErr(e2 instanceof ApiError ? e2.message : "تعذّر حفظ المحتوى.");
    } finally {
      setSaving(false);
    }
  };

  const refHint = editing && item.video ? "اتركه فارغًا للإبقاء على الفيديو الحالي. " + REF_HINT[provider] : REF_HINT[provider];

  return (
    <Modal title={editing ? "تعديل المحتوى" : "محتوى جديد"} onClose={onClose}>
      <form onSubmit={submit} className="dash-form">
        {err && <Banner tone="err">{err}</Banner>}
        <Field label="العنوان" required error={fe.title}>
          <TextInput value={title} onChange={(e) => setTitle(e.target.value)} autoFocus />
        </Field>
        <Field label="الوصف (اختياري)">
          <textarea className="inp" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <Field label="الصف (اختياري)" error={fe.grade_id}>
          <select className="inp" value={gradeId} onChange={(e) => setGradeId(e.target.value)}>
            <option value="">محتوى عام</option>
            {grades.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
          </select>
        </Field>
        <Field label="الفيديو">
          <select className="inp" value={provider} onChange={(e) => setProvider(e.target.value)}>
            {PROVIDERS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
          </select>
        </Field>
        {provider !== "none" && (
          <Field label="معرّف الفيديو" hint={refHint} error={fe.video_ref}>
            <input className="inp" dir="ltr" value={ref} onChange={(e) => setRef(e.target.value)} autoComplete="off" spellCheck={false} />
          </Field>
        )}
        <Btn type="submit" loading={saving} loadingText="جارٍ الحفظ…">{editing ? "حفظ التعديلات" : "إضافة المحتوى"}</Btn>
      </form>
    </Modal>
  );
}

function VideoModal({ item, onClose }) {
  const url = item.video?.embed_url;
  // Defense in depth: the backend only ever builds https embed URLs from a
  // strictly-validated id, and we still refuse to frame anything else.
  const safe = typeof url === "string" && url.startsWith("https://");
  return (
    <Modal title={item.title} onClose={onClose}>
      {safe ? (
        <div style={{ position: "relative", paddingTop: "56.25%" }}>
          <iframe
            title={item.title} src={url}
            style={{ position: "absolute", inset: 0, width: "100%", height: "100%", border: 0, borderRadius: 12 }}
            sandbox="allow-scripts allow-same-origin allow-presentation"
            allow="fullscreen" allowFullScreen referrerPolicy="no-referrer" loading="lazy"
          />
        </div>
      ) : (
        <Banner tone="err">تعذّر عرض الفيديو.</Banner>
      )}
    </Modal>
  );
}

function ConfirmDeleteModal({ item, onClose, onDeleted }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const run = async () => {
    setBusy(true); setErr(null);
    try { await contentApi.remove(item.id); onDeleted(); }
    catch (e) { setErr(e instanceof ApiError ? e.message : "تعذّر الحذف."); setBusy(false); }
  };
  return (
    <Modal title="حذف المحتوى" text={`سيتم حذف «${item.title}» نهائيًا ولا يمكن التراجع.`} onClose={onClose}>
      <div className="dash-form">
        {err && <Banner tone="err">{err}</Banner>}
        <Btn onClick={run} loading={busy} loadingText="جارٍ الحذف…">نعم، احذف</Btn>
        <Btn variant="ghost" onClick={onClose} disabled={busy}>إلغاء</Btn>
      </div>
    </Modal>
  );
}

export default function ContentPage() {
  const { grades } = useGrades();
  const [search, setSearch] = useState("");
  const debounced = useDebounced(search);
  const [gradeFilter, setGradeFilter] = useState("");
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState(null);
  const [modal, setModal] = useState(null); // {type:"form"|"video"|"delete", item?}

  const load = () => {
    setStatus((s) => (s === "ready" ? "ready" : "loading"));
    contentApi.list({ search: debounced, grade_id: gradeFilter })
      .then((d) => { setItems(d.results || d); setStatus("ready"); })
      .catch((e) => { setError(e instanceof ApiError ? e.message : "حدث خطأ أثناء تحميل البيانات."); setStatus("error"); });
  };
  useEffect(load, [debounced, gradeFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  const filtered = debounced || gradeFilter;

  return (
    <>
      <div className="dash-section-head">
        <h2>المحتوى التعليمي</h2>
        <Btn onClick={() => setModal({ type: "form" })}><Plus size={16} /> محتوى جديد</Btn>
      </div>

      <div className="dash-filters">
        <div className="dash-search">
          <Search size={16} />
          <input placeholder="ابحث في العناوين" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <select className="inp" value={gradeFilter} onChange={(e) => setGradeFilter(e.target.value)}>
          <option value="">كل الصفوف</option>
          {grades.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
        </select>
      </div>

      {status === "loading" && <p className="field-msg">جاري تحميل البيانات...</p>}
      {status === "error" && <Banner tone="err">{error}</Banner>}

      {status === "ready" && items.length === 0 && (
        <ComingSoon
          title={filtered ? "لا نتائج مطابقة" : "لا يوجد محتوى بعد"}
          text={filtered ? "جرّب تعديل البحث أو الفلتر." : "أضف أول محتوى تعليمي — نصًا أو مع فيديو."}
        />
      )}

      {status === "ready" && items.length > 0 && (
        <div className="dash-cards">
          {items.map((c) => (
            <div key={c.id} className="dash-card">
              <div className="k"><BookOpen size={14} /> {c.grade?.name || "محتوى عام"}</div>
              <div className="v" style={{ fontSize: "1.05rem" }}>{c.title}</div>
              {c.description && <p className="dash-clamp">{c.description}</p>}
              <div className="dash-session-actions" style={{ marginTop: 10 }}>
                {c.video && <Btn variant="secondary" onClick={() => setModal({ type: "video", item: c })}><Play size={14} /> تشغيل</Btn>}
                <Btn variant="ghost" onClick={() => setModal({ type: "form", item: c })} aria-label="تعديل"><Pencil size={14} /></Btn>
                <Btn variant="ghost" onClick={() => setModal({ type: "delete", item: c })} aria-label="حذف"><Trash2 size={14} /></Btn>
              </div>
            </div>
          ))}
        </div>
      )}

      {modal?.type === "form" && (
        <ContentFormModal item={modal.item} grades={grades} onClose={() => setModal(null)} onSaved={() => { setModal(null); load(); }} />
      )}
      {modal?.type === "video" && <VideoModal item={modal.item} onClose={() => setModal(null)} />}
      {modal?.type === "delete" && (
        <ConfirmDeleteModal item={modal.item} onClose={() => setModal(null)} onDeleted={() => { setModal(null); load(); }} />
      )}
    </>
  );
}

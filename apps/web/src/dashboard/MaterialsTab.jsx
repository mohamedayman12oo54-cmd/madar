import { useEffect, useRef, useState } from "react";
import { AlertCircle, Eye, FileText, NotebookPen, Pencil, Plus, Send, Trash2, UploadCloud, X } from "lucide-react";
import { Banner, Btn, Field, Modal, TextInput } from "../auth/ui.jsx";
import DocumentOpener from "../components/DocumentOpener.jsx";
import SummaryText from "../components/SummaryText.jsx";
import { contentApi } from "../lib/dashboardApi.js";
import { ApiError } from "../lib/api.js";
import { formatBytes } from "../lib/files.js";
import { MAX_SUMMARY_CHARS } from "../lib/summary.js";
import { useGrades } from "./useGrades.js";
import { useGroups } from "./useGroups.js";
import { Confirm, Empty, MultiSelect, toggleId } from "./common.jsx";
import "./materials.css";

const MAX_PDF_BYTES = 50 * 1024 * 1024;
const listOf = (d) => (Array.isArray(d) ? d : d?.results || []);
const audienceCount = (t) => t.grades.length + t.groups.length + t.students.length;

// Everything that differs between the two sections lives here, so the list, the form and the
// publishing flow are one piece of code.
const COPY = {
  pdf: {
    icon: FileText,
    add: "رفع ملف PDF",
    formAdd: "رفع ملف PDF",
    formEdit: "تعديل الملف",
    titleLabel: "عنوان الملف",
    titlePlaceholder: "مثال: ورقة عمل الدرس الثالث",
    emptyTitle: "لا توجد ملفات PDF بعد",
    emptyText: "ارفع شرح الدرس أو ورقة العمل، ثم حدّد من يراها وانشرها.",
  },
  summary: {
    icon: NotebookPen,
    add: "كتابة ملخص",
    formAdd: "ملخص أو ملاحظات جديدة",
    formEdit: "تعديل الملخص",
    titleLabel: "عنوان الملخص",
    titlePlaceholder: "مثال: ملخص الباب الأول",
    emptyTitle: "لا توجد ملخصات بعد",
    emptyText: "اكتب ملخص الدرس أو ملاحظاتك للطلاب، ثم حدّد من يراه وانشره.",
  },
};

function MaterialForm({ kind, item, grades, groups, onClose, onSaved }) {
  const copy = COPY[kind];
  const [title, setTitle] = useState(item?.title || "");
  const [description, setDescription] = useState(item?.description || "");
  const [body, setBody] = useState("");
  const [bodyLoaded, setBodyLoaded] = useState(kind !== "summary" || !item);
  const [file, setFile] = useState(null);
  const [dropFile, setDropFile] = useState(false);
  const [gradeIds, setGradeIds] = useState(item?.targets.grades.map((g) => g.id) || []);
  const [groupIds, setGroupIds] = useState(item?.targets.groups.map((g) => g.id) || []);
  const [err, setErr] = useState(null);
  const [fe, setFe] = useState({});
  const [saving, setSaving] = useState(false);
  const picker = useRef(null);
  const gradeName = Object.fromEntries(grades.map((g) => [g.id, g.name]));

  // The list never carries the summary text (it can be 20k characters); fetch it when editing.
  useEffect(() => {
    if (kind !== "summary" || !item) return undefined;
    let alive = true;
    contentApi
      .get(item.id)
      .then((d) => alive && (setBody(d.body || ""), setBodyLoaded(true)))
      .catch(() => alive && setErr("تعذّر تحميل نص الملخص."));
    return () => {
      alive = false;
    };
  }, [kind, item]);

  const hadFile = Boolean(item?.has_document) && !dropFile;

  const pick = (f) => {
    setFe((x) => ({ ...x, file: null }));
    if (!f) return;
    if (!/\.pdf$/i.test(f.name)) return setFe((x) => ({ ...x, file: "الصيغة المسموحة: PDF فقط." }));
    if (f.size > MAX_PDF_BYTES)
      return setFe((x) => ({ ...x, file: `حجم الملف يتجاوز ${formatBytes(MAX_PDF_BYTES)}.` }));
    setFile(f);
    setDropFile(false);
  };

  const save = async () => {
    setErr(null);
    const problems = {};
    if (!title.trim()) problems.title = "اكتب عنوانًا.";
    if (kind === "summary" && !body.trim()) problems.body = "اكتب نص الملخص.";
    if (Object.keys(problems).length) return setFe(problems);
    setFe({});
    setSaving(true);
    try {
      const payload = {
        kind,
        title: title.trim(),
        description,
        grade_ids: gradeIds,
        group_ids: groupIds,
        enrollment_ids: item ? item.targets.students.map((s) => s.id) : [],
        ...(kind === "summary" ? { body } : {}),
      };
      let saved;
      if (item) {
        const { kind: _fixed, ...patch } = payload; // the kind never changes after creation
        saved = await contentApi.update(item.id, patch);
      } else {
        saved = await contentApi.create(payload);
      }
      if (kind === "pdf") {
        if (item && dropFile && !file && item.has_document) await contentApi.removeDocument(item.id);
        if (file) await contentApi.uploadDocument(saved.id, file);
      }
      onSaved(saved);
    } catch (e) {
      if (e instanceof ApiError && e.fields) {
        setFe(Object.fromEntries(Object.entries(e.fields).map(([k, v]) => [k, [].concat(v).join(" ")])));
        setErr(e.message);
      } else {
        setErr(e instanceof ApiError ? e.message : "تعذّر الحفظ، حاول مرة أخرى.");
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      size="lg"
      title={item ? copy.formEdit : copy.formAdd}
      onClose={onClose}
      footer={
        <>
          <Btn variant="ghost" onClick={onClose}>
            إلغاء
          </Btn>
          <Btn onClick={save} loading={saving} disabled={!bodyLoaded}>
            حفظ
          </Btn>
        </>
      }
    >
      {err && <Banner tone="err">{err}</Banner>}
      <div className="mat-form">
        <Field label={copy.titleLabel} required error={fe.title}>
          <TextInput value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} placeholder={copy.titlePlaceholder} />
        </Field>
        <Field label="وصف قصير (اختياري)" hint="يظهر للطالب تحت العنوان.">
          <TextInput value={description} onChange={(e) => setDescription(e.target.value)} maxLength={500} />
        </Field>

        {kind === "pdf" && (
          <div className="mat-file">
            <span className="mat-label">ملف الدرس</span>
            {file || hadFile ? (
              <div className="mat-file-card">
                <FileText size={20} aria-hidden="true" />
                <div className="mat-file-meta">
                  <strong dir="auto">{file ? file.name : item.original_filename || "ملف PDF"}</strong>
                  <small>{formatBytes(file ? file.size : item.file_size)}</small>
                </div>
                <button
                  type="button"
                  className="mini-btn"
                  onClick={() => picker.current?.click()}
                >
                  استبدال
                </button>
                <button
                  type="button"
                  className="mini-btn danger"
                  aria-label="إزالة الملف"
                  onClick={() => {
                    setFile(null);
                    setDropFile(true);
                  }}
                >
                  <X size={13} />
                </button>
              </div>
            ) : (
              <button type="button" className="mat-drop" onClick={() => picker.current?.click()}>
                <UploadCloud size={26} aria-hidden="true" />
                <strong>اضغط لاختيار ملف PDF</strong>
                <small>حتى {formatBytes(MAX_PDF_BYTES)} — يفتحه الطالب من صفحته عبر رابط مؤقت محمي.</small>
              </button>
            )}
            <input
              ref={picker}
              type="file"
              accept="application/pdf,.pdf"
              hidden
              onChange={(e) => {
                pick(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
            {fe.file && <p className="field-err">{fe.file}</p>}
          </div>
        )}

        {kind === "summary" && (
          <Field
            label="نص الملخص"
            required
            error={fe.body}
            hint="اكتب بحرية. للتنسيق: «# عنوان» لعنوان كبير، «## عنوان» لفرعي، «- نقطة» لقائمة، «1. خطوة» لقائمة مرقّمة."
          >
            <textarea
              className="inp mat-body"
              rows={12}
              dir="auto"
              value={body}
              maxLength={MAX_SUMMARY_CHARS}
              disabled={!bodyLoaded}
              onChange={(e) => setBody(e.target.value)}
              placeholder={bodyLoaded ? "# ملخص الدرس\n- أهم فكرة\n- قانون يجب حفظه" : "جارٍ التحميل…"}
            />
            <small className="mat-count">
              {body.length.toLocaleString("ar-EG")} / {MAX_SUMMARY_CHARS.toLocaleString("ar-EG")}
            </small>
          </Field>
        )}

        <div className="mat-audience">
          <h4>من يرى هذا؟</h4>
          <p className="field-msg">اختر الصف ثم المجموعة. بلا مستهدفين يبقى مسودة لا يراها أحد.</p>
          <div className="audience-row">
            <Field label="الصفوف">
              <MultiSelect
                label="الصفوف"
                items={grades.map((g) => ({ id: g.id, name: g.name }))}
                selected={gradeIds}
                onToggle={(id) => setGradeIds((l) => toggleId(l, id))}
                onClear={() => setGradeIds([])}
                placeholder="اختر الصف…"
                searchPlaceholder="ابحث عن صف…"
                empty="لا توجد صفوف بعد."
              />
            </Field>
            <Field label="المجموعات">
              <MultiSelect
                label="المجموعات"
                items={groups.map((g) => ({ id: g.id, name: g.name, hint: gradeName[g.grade_id] }))}
                selected={groupIds}
                onToggle={(id) => setGroupIds((l) => toggleId(l, id))}
                onClear={() => setGroupIds([])}
                placeholder="اختر المجموعة…"
                searchPlaceholder="ابحث عن مجموعة…"
                empty="لا توجد مجموعات بعد."
              />
            </Field>
          </div>
        </div>
      </div>
    </Modal>
  );
}

function SummaryPreview({ item, onClose }) {
  const [body, setBody] = useState(null);
  useEffect(() => {
    contentApi.get(item.id).then((d) => setBody(d.body || "")).catch(() => setBody(""));
  }, [item.id]);
  return (
    <Modal size="md" title={item.title} text={item.description} onClose={onClose}>
      {body === null ? <p className="field-msg">جارٍ التحميل…</p> : <SummaryText text={body} />}
    </Modal>
  );
}

/** The teacher's "PDF files" and "summaries & notes" sections of the content hub. */
export default function MaterialsTab({ kind }) {
  const copy = COPY[kind];
  const Icon = copy.icon;
  const { grades } = useGrades();
  const { groups } = useGroups();
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState(null);
  const [form, setForm] = useState(null);
  const [view, setView] = useState(null);
  const [pub, setPub] = useState(null);
  const [del, setDel] = useState(null);
  const [notice, setNotice] = useState(null);
  const [filter, setFilter] = useState("");

  const load = () =>
    contentApi
      .list({ kind, published: filter })
      .then((d) => {
        setRows(listOf(d));
        setErr(null);
      })
      .catch((e) => setErr(e instanceof ApiError ? e.message : "تعذّر تحميل المحتوى."));
  useEffect(() => {
    setRows(null);
    load();
  }, [kind, filter]); // eslint-disable-line react-hooks/exhaustive-deps

  const ready = (it) => (kind === "pdf" ? it.has_document : it.has_body);
  const missing = (it) =>
    !ready(it)
      ? kind === "pdf"
        ? "لم يُرفع ملف بعد — افتح «تعديل» وارفع الملف."
        : "لم تكتب النص بعد — افتح «تعديل» واكتب الملخص."
      : audienceCount(it.targets) === 0
        ? "حدّد الصف أو المجموعة من «تعديل» ثم اضغط «نشر»."
        : "جاهز للنشر — اضغط «نشر» ليظهر للطلاب.";

  return (
    <>
      <div className="mat-head">
        <p className="mat-sub">
          {kind === "pdf"
            ? "ارفع ملفات PDF للدرس. يفتحها الطالب من صفحته عبر رابط مؤقت محمي."
            : "اكتب ملخصات الدروس وملاحظاتك. يقرؤها الطالب داخل التطبيق بخط مريح."}
        </p>
        <Btn onClick={() => setForm("add")}>
          <Plus size={16} /> {copy.add}
        </Btn>
      </div>
      {notice && <Banner tone={notice.tone}>{notice.text}</Banner>}
      <div className="dash-filters">
        <select className="inp" value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="تصفية">
          <option value="">الكل</option>
          <option value="1">المنشور</option>
          <option value="0">المسودات</option>
        </select>
      </div>
      {err && <Banner tone="err">{err}</Banner>}
      {!rows && !err && <p className="field-msg">جاري التحميل...</p>}
      {rows && rows.length === 0 && <Empty title={copy.emptyTitle} text={copy.emptyText} icon={Icon} />}
      <div className="list-rows">
        {(rows || []).map((it) => (
          <div key={it.id} className="list-row">
            <div>
              <strong>{it.title}</strong>{" "}
              <span className={"chip-s " + (it.published ? "good" : "warn")}>{it.published ? "منشور" : "مسودة"}</span>
              <div className="stat-sub">
                {kind === "pdf" && it.has_document ? `${it.original_filename || "ملف PDF"} • ${formatBytes(it.file_size)} • ` : ""}
                {audienceCount(it.targets) === 0
                  ? "بلا مستهدفين"
                  : [
                      ...it.targets.grades.map((g) => `صف: ${g.name}`),
                      ...it.targets.groups.map((g) => `مجموعة: ${g.name}`),
                      it.targets.students.length ? `${it.targets.students.length} طالب` : null,
                    ]
                      .filter(Boolean)
                      .join(" • ")}
              </div>
            </div>
            {!it.published && (
              <div className="draft-hint">
                <AlertCircle size={14} />
                <span>{missing(it)}</span>
              </div>
            )}
            <div className="row-actions">
              {kind === "pdf" && it.has_document && (
                <DocumentOpener getTicket={() => contentApi.documentTicket(it.id)} label="معاينة" primary={false} />
              )}
              {kind === "summary" && it.has_body && (
                <button className="mini-btn" onClick={() => setView(it)}>
                  <Eye size={13} /> معاينة
                </button>
              )}
              {!it.published && (
                <button
                  className={"mini-btn" + (ready(it) && audienceCount(it.targets) > 0 ? " is-primary" : "")}
                  onClick={() => setPub(it)}
                >
                  <Send size={13} /> نشر
                </button>
              )}
              <button className="mini-btn" onClick={() => setForm(it)}>
                <Pencil size={13} /> تعديل
              </button>
              <button className="mini-btn danger" aria-label="حذف" onClick={() => setDel(it)}>
                <Trash2 size={13} />
              </button>
            </div>
          </div>
        ))}
      </div>

      {form && (
        <MaterialForm
          kind={kind}
          item={form === "add" ? null : form}
          grades={grades}
          groups={groups}
          onClose={() => setForm(null)}
          onSaved={() => {
            setForm(null);
            load();
          }}
        />
      )}
      {view && <SummaryPreview item={view} onClose={() => setView(null)} />}
      {pub && (
        <Confirm
          title="نشر المحتوى؟"
          confirmLabel="نشر الآن"
          text={`سيظهر «${pub.title}» للمستهدفين ويصل الطلاب النشطين إشعار مرة واحدة.`}
          onClose={() => setPub(null)}
          onConfirm={async () => {
            try {
              const r = await contentApi.publish(pub.id);
              setNotice({ tone: "info", text: `تم النشر وإشعار ${r.notified} طالب.` });
            } catch (e) {
              setNotice({ tone: "err", text: e instanceof ApiError ? e.message : "تعذّر النشر." });
            }
            setPub(null);
            load();
          }}
        />
      )}
      {del && (
        <Confirm
          danger
          title="حذف المحتوى"
          confirmLabel="حذف"
          text={`سيُحذف «${del.title}» نهائيًا ولا يمكن التراجع.`}
          onClose={() => setDel(null)}
          onConfirm={async () => {
            await contentApi.remove(del.id).catch(() => {});
            setDel(null);
            load();
          }}
        />
      )}
    </>
  );
}

import { useCallback, useEffect, useId, useState } from "react";
import { ChevronLeft, ChevronRight, Eye, EyeOff, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { Banner, Btn, Field, Modal, TextInput } from "../auth/ui.jsx";
import { ApiError } from "../lib/api.js";
import { knowledgeApi } from "../lib/knowledgeApi.js";
import { Confirm, Empty, PageHeader, fmtDate, useDebounced } from "../dashboard/common.jsx";

const STATUS = {
  draft: { label: "مسودة", tone: "warn" },
  published: { label: "منشورة", tone: "good" },
};
const FILTERS = [
  ["", "الكل"],
  ["draft", "مسودات"],
  ["published", "منشورة"],
];
const PAGE_SIZE = 20;

const fieldErrors = (e) =>
  e instanceof ApiError && e.fields
    ? Object.fromEntries(Object.entries(e.fields).map(([k, v]) => [k, [].concat(v).join(" ")]))
    : {};

/** Create / edit one document. Status and version are never sent: the server owns the lifecycle. */
function DocumentForm({ doc, onClose, onSaved }) {
  const formId = useId();
  const [title, setTitle] = useState(doc?.title || "");
  const [topic, setTopic] = useState(doc?.topic || "");
  const [body, setBody] = useState(doc?.body || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [fe, setFe] = useState({});

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setFe({});
    try {
      const payload = { title, topic, body };
      const saved = doc ? await knowledgeApi.update(doc.id, payload) : await knowledgeApi.create(payload);
      onSaved(saved, !doc);
    } catch (err) {
      const fields = fieldErrors(err);
      setFe(fields);
      setError(
        Object.keys(fields).length
          ? "راجع الحقول المحددة أدناه."
          : err instanceof ApiError
            ? err.message
            : "تعذّر الحفظ. تحقق من الاتصال وحاول مرة أخرى."
      );
    } finally {
      setBusy(false);
    }
  };

  const published = doc?.status === "published";
  return (
    <Modal
      size="md"
      title={doc ? "تعديل المادة" : "مادة جديدة"}
      text={
        published
          ? "هذه المادة منشورة ويعتمد عليها المساعد الدراسي الآن. أي تعديل في نصها يسري فورًا ويرفع رقم إصدارها."
          : "تبدأ المادة كمسودة ولا يعتمد عليها المساعد الدراسي حتى تنشرها."
      }
      onClose={onClose}
      footer={
        <>
          <Btn variant="ghost" onClick={onClose}>
            إلغاء
          </Btn>
          <Btn type="submit" form={formId} loading={busy} loadingText="جاري الحفظ…">
            حفظ
          </Btn>
        </>
      }
    >
      <form id={formId} className="form-grid" onSubmit={submit} noValidate>
        {error && (
          <div className="form-wide">
            <Banner tone="err">{error}</Banner>
          </div>
        )}
        <Field className="form-wide" label="العنوان" required error={fe.title}>
          <TextInput
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={200}
            autoFocus
            placeholder="مثال: قانون نيوتن الأول"
          />
        </Field>
        <Field
          className="form-wide"
          label="الموضوع (اختياري)"
          hint="وسم قصير يساعد في ربط المادة بأسئلة الطلاب."
          error={fe.topic}
        >
          <TextInput value={topic} onChange={(e) => setTopic(e.target.value)} maxLength={120} />
        </Field>
        <Field
          className="form-wide"
          label="نص المادة"
          required
          hint="20 حرفًا على الأقل. اكتب المعلومة نفسها بوضوح؛ هذا هو النص الذي يعتمد عليه المساعد."
          error={fe.body}
        >
          <textarea
            className={"inp" + (fe.body ? " err" : "")}
            rows={10}
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
        </Field>
      </form>
    </Modal>
  );
}

/** Knowledge Base authoring for the Content Maintainer. The KB is central (not tenant-scoped); only
 *  PUBLISHED documents ever ground an AI answer, so publishing is a deliberate, separate step. */
export default function KnowledgePage() {
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const q = useDebounced(search);
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null); // { count, results }
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [editing, setEditing] = useState(null); // null | "new" | doc
  const [removing, setRemoving] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const searchId = useId();

  const load = useCallback(() => {
    return knowledgeApi
      .list({ status, search: q.trim(), page: page > 1 ? page : "" })
      .then((d) => {
        setData(Array.isArray(d) ? { count: d.length, results: d } : d);
        setError(null);
      })
      .catch((e) => {
        // Asking for a page that no longer exists (the last row of the last page was deleted) is not a
        // failure worth showing: step back to the previous page.
        if (e instanceof ApiError && e.status === 404 && page > 1) {
          setPage((p) => Math.max(1, p - 1));
          return;
        }
        setError(e instanceof ApiError ? e.message : "تعذّر تحميل المواد.");
      });
  }, [status, q, page]);

  useEffect(() => {
    load();
  }, [load]);

  // A new filter or search always starts from the first page.
  useEffect(() => {
    setPage(1);
  }, [status, q]);

  const toggle = async (doc) => {
    setBusyId(doc.id);
    setNotice(null);
    try {
      const next = doc.status === "published" ? await knowledgeApi.unpublish(doc.id) : await knowledgeApi.publish(doc.id);
      setNotice({
        tone: "good",
        text:
          next.status === "published"
            ? `نُشرت «${next.title}» (الإصدار ${next.version}). يعتمد عليها المساعد الدراسي الآن.`
            : `سُحبت «${next.title}» من الاعتماد وعادت مسودة.`,
      });
      await load();
    } catch (e) {
      setNotice({ tone: "err", text: e instanceof ApiError ? e.message : "تعذّر تنفيذ العملية." });
    } finally {
      setBusyId(null);
    }
  };

  const remove = async () => {
    try {
      await knowledgeApi.remove(removing.id);
      setNotice({ tone: "good", text: `حُذفت «${removing.title}».` });
      setRemoving(null);
      await load();
    } catch (e) {
      setRemoving(null);
      setNotice({ tone: "err", text: e instanceof ApiError ? e.message : "تعذّر الحذف." });
    }
  };

  const onSaved = (saved, created) => {
    setEditing(null);
    setNotice({ tone: "good", text: created ? "أُضيفت المادة كمسودة." : "حُفظت التعديلات." });
    load();
  };

  const rows = data?.results || [];
  const pages = Math.max(1, Math.ceil((data?.count || 0) / PAGE_SIZE));
  const filtered = Boolean(status || q.trim());

  return (
    <>
      <PageHeader infoKey="team_knowledge" title="قاعدة المعرفة" count={data?.count}>
        <Btn onClick={() => setEditing("new")}>
          <Plus size={16} aria-hidden="true" /> مادة جديدة
        </Btn>
      </PageHeader>

      {notice && <Banner tone={notice.tone}>{notice.text}</Banner>}

      <div className="dash-filters">
        <div className="seg" role="group" aria-label="تصفية حسب الحالة">
          {FILTERS.map(([value, label]) => (
            <button
              key={value || "all"}
              type="button"
              className={status === value ? "active" : ""}
              aria-pressed={status === value}
              onClick={() => setStatus(value)}
            >
              {label}
            </button>
          ))}
        </div>
        <label className="dash-search" htmlFor={searchId}>
          <Search size={16} aria-hidden="true" />
          <input
            id={searchId}
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="ابحث في عناوين المواد"
          />
        </label>
      </div>

      {error ? (
        <div role="alert">
          <Empty title="تعذّر التحميل" text={error} />
          <Btn variant="ghost" onClick={load}>
            إعادة المحاولة
          </Btn>
        </div>
      ) : !data ? (
        <p className="field-msg" role="status">
          جاري التحميل...
        </p>
      ) : rows.length === 0 ? (
        <Empty
          title={filtered ? "لا توجد نتائج" : "لا توجد مواد بعد"}
          text={
            filtered
              ? "غيّر التصفية أو كلمة البحث."
              : "أضف أول مادة. تبدأ كمسودة ولا يستخدمها المساعد الدراسي حتى تنشرها."
          }
        />
      ) : (
        <ul className="list-rows" style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {rows.map((doc) => {
            const st = STATUS[doc.status] || { label: doc.status, tone: "" };
            return (
              <li key={doc.id} className="list-row">
                <div style={{ minWidth: 0, flex: "1 1 220px" }}>
                  <strong style={{ overflowWrap: "anywhere" }}>{doc.title}</strong>
                  <div className="stat-sub">
                    {doc.topic ? `${doc.topic} • ` : ""}الإصدار {doc.version} • آخر تحديث {fmtDate(doc.updated_at)}
                  </div>
                </div>
                <span className={"chip-s " + st.tone}>{st.label}</span>
                <div className="dash-head-actions">
                  <button type="button" className="mini-btn" onClick={() => setEditing(doc)}>
                    <Pencil size={14} aria-hidden="true" /> تعديل
                  </button>
                  <button
                    type="button"
                    className="mini-btn"
                    disabled={busyId === doc.id}
                    onClick={() => toggle(doc)}
                  >
                    {doc.status === "published" ? (
                      <>
                        <EyeOff size={14} aria-hidden="true" /> سحب
                      </>
                    ) : (
                      <>
                        <Eye size={14} aria-hidden="true" /> نشر
                      </>
                    )}
                  </button>
                  <button type="button" className="mini-btn danger" onClick={() => setRemoving(doc)}>
                    <Trash2 size={14} aria-hidden="true" /> حذف
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {data && pages > 1 && (
        <nav className="dash-head-actions" aria-label="التنقل بين الصفحات" style={{ marginBlockStart: 14 }}>
          <button
            type="button"
            className="mini-btn"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            <ChevronRight size={14} aria-hidden="true" /> السابق
          </button>
          <span className="stat-sub" aria-live="polite">
            صفحة {page} من {pages}
          </span>
          <button
            type="button"
            className="mini-btn"
            disabled={page >= pages}
            onClick={() => setPage((p) => p + 1)}
          >
            التالي <ChevronLeft size={14} aria-hidden="true" />
          </button>
        </nav>
      )}

      {editing && (
        <DocumentForm
          doc={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={onSaved}
        />
      )}
      {removing && (
        <Confirm
          danger
          title="حذف المادة"
          text={`ستُحذف «${removing.title}» نهائيًا${
            removing.status === "published" ? " ولن يعتمد عليها المساعد الدراسي بعد الآن" : ""
          }. لا يمكن التراجع.`}
          confirmLabel="حذف"
          onConfirm={remove}
          onClose={() => setRemoving(null)}
        />
      )}
    </>
  );
}

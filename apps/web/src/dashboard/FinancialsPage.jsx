import { useEffect, useState } from "react";
import { Wallet, Plus } from "lucide-react";
import { Field, TextInput, Btn, Banner, Modal } from "../auth/ui.jsx";
import { paymentsApi, financialSummaryApi } from "../lib/financialsApi.js";
import { ApiError } from "../lib/api.js";
import { useGrades } from "./useGrades.js";
import ComingSoon from "./ComingSoon.jsx";

function money(v) {
  return Number(v).toLocaleString("ar-EG", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function AddPaymentModal({ row, onClose, onSaved }) {
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [err, setErr] = useState(null);
  const [saving, setSaving] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setErr(null);
    if (!amount || Number(amount) <= 0) { setErr("أدخل قيمة أكبر من صفر."); return; }
    setSaving(true);
    try {
      await paymentsApi.create({ enrollment_id: row.enrollment_id, amount, note: note.trim() || undefined });
      onSaved();
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "تعذّر تسجيل الدفعة.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title={`تسجيل دفعة — ${row.student.name}`} text={`المتبقي حاليًا: ${money(row.outstanding)} جنيه`} onClose={onClose}>
      <form onSubmit={submit} className="dash-form">
        {err && <Banner tone="err">{err}</Banner>}
        <Field label="القيمة (جنيه)" required>
          <TextInput type="number" min="0.01" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} autoFocus />
        </Field>
        <Field label="ملاحظة (اختياري)">
          <TextInput value={note} onChange={(e) => setNote(e.target.value)} placeholder="مثال: دفعة الشهر الأول" />
        </Field>
        <Btn type="submit" loading={saving} loadingText="جارٍ الحفظ…">تسجيل الدفعة</Btn>
      </form>
    </Modal>
  );
}

export default function FinancialsPage() {
  const { grades, status: gradesStatus } = useGrades();
  const [gradeId, setGradeId] = useState("");
  const [rows, setRows] = useState([]);
  const [status, setStatus] = useState("loading");
  const [error, setError] = useState(null);
  const [payFor, setPayFor] = useState(null);

  const load = () => {
    setStatus((s) => (s === "ready" ? "ready" : "loading"));
    financialSummaryApi.get({ grade_id: gradeId })
      .then((data) => { setRows(data); setStatus("ready"); })
      .catch((e) => { setError(e instanceof ApiError ? e.message : "تعذّر تحميل البيانات المالية."); setStatus("error"); });
  };

  useEffect(load, [gradeId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (gradesStatus === "ready" && grades.length === 0) {
    return <ComingSoon title="لا توجد صفوف بعد" text="أضف صفًا دراسيًا وحدد رسومه من صفحة «المجموعات» أولًا." />;
  }

  return (
    <>
      <div className="dash-section-head"><h2>المدفوعات</h2></div>

      <div className="dash-filters">
        <select className="inp" value={gradeId} onChange={(e) => setGradeId(e.target.value)}>
          <option value="">كل الصفوف</option>
          {grades.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
        </select>
      </div>

      {status === "loading" && <p className="field-msg">جاري تحميل البيانات...</p>}
      {status === "error" && <Banner tone="err">{error}</Banner>}

      {status === "ready" && rows.length === 0 && (
        <ComingSoon title="لا يوجد طلاب لعرض بياناتهم المالية" text="أضف طلابًا لهذا الصف من صفحة «الطلاب»." />
      )}

      {status === "ready" && rows.length > 0 && (
        <div className="dash-table-wrap">
          <table className="dash-table">
            <thead>
              <tr><th>الطالب</th><th>الصف</th><th>الرسوم</th><th>المدفوع</th><th>المتبقي</th><th></th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.enrollment_id}>
                  <td>{r.student.name}</td>
                  <td>{r.grade_name}</td>
                  <td className="ltr-cell">{money(r.fee_amount)}</td>
                  <td className="ltr-cell">{money(r.paid_total)}</td>
                  <td className="ltr-cell">
                    <span className={"dash-pill" + (Number(r.outstanding) <= 0 ? " on" : "")}>
                      {Number(r.outstanding) <= 0 ? "مسدد بالكامل" : money(r.outstanding)}
                    </span>
                  </td>
                  <td>
                    <Btn variant="ghost" onClick={() => setPayFor(r)}><Plus size={14} /> دفعة</Btn>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {payFor && (
        <AddPaymentModal row={payFor} onClose={() => setPayFor(null)} onSaved={() => { setPayFor(null); load(); }} />
      )}
    </>
  );
}

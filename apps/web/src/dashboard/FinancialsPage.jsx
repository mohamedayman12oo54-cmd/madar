import { useEffect, useState } from "react";
import { Search, History } from "lucide-react";
import { Banner, Modal } from "../auth/ui.jsx";
import { financialsApi } from "../lib/dashboardApi.js";
import { ApiError } from "../lib/api.js";
import { useGrades } from "./useGrades.js";
import { useGroups } from "./useGroups.js";
import {
  Empty,
  MonthInput,
  PageHeader,
  currentMonthValue,
  fmtDateTime,
  fmtMonth,
  fmtMoney,
  useDebounced,
} from "./common.jsx";

function HistoryModal({ row, onClose }) {
  const [items, setItems] = useState(null);
  useEffect(() => {
    financialsApi
      .history(row.enrollment_id)
      .then((d) => setItems(Array.isArray(d) ? d : d.results || []))
      .catch(() => setItems([]));
  }, [row.enrollment_id]);
  return (
    <Modal
      size="md"
      title={`سجل مدفوعات ${row.name}`}
      text="الأشهر المسجّلة فقط. الشهر غير المسجل يُعدّ غير مدفوع."
      onClose={onClose}
    >
      {items === null ? (
        <p className="field-msg">جاري التحميل...</p>
      ) : items.length === 0 ? (
        <p className="field-msg">لا توجد أشهر مسجلة.</p>
      ) : (
        <div className="list-rows">
          {items.map((p) => (
            <div key={p.id} className="list-row">
              <strong>{fmtMonth(p.month)}</strong>
              <span className={"chip-s " + (p.status === "paid" ? "good" : "bad")}>
                {p.status === "paid" ? "مدفوع" : "غير مدفوع"} — {fmtMoney(p.amount)}
              </span>
              {p.paid_at && <span className="stat-sub">{fmtDateTime(p.paid_at)}</span>}
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}

export default function FinancialsPage() {
  const { grades } = useGrades();
  const { groups } = useGroups();
  const [month, setMonth] = useState(currentMonthValue());
  const [gradeId, setGradeId] = useState("");
  const [groupId, setGroupId] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [search, setSearch] = useState("");
  const q = useDebounced(search);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(null);
  const [history, setHistory] = useState(null);

  const load = () =>
    financialsApi
      .sheet({ month, grade_id: gradeId, group_id: groupId, status: statusFilter, search: q })
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) =>
        setError(
          e instanceof ApiError
            ? e.fields
              ? Object.values(e.fields).flat().join(" ")
              : e.message
            : "تعذّر تحميل المدفوعات."
        )
      );
  useEffect(() => {
    load();
  }, [month, gradeId, groupId, statusFilter, q]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = async (row) => {
    const next = row.status === "paid" ? "unpaid" : "paid";
    setSaving(row.enrollment_id);
    try {
      await financialsApi.mark(row.enrollment_id, month, next);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "تعذّر الحفظ.");
    } finally {
      setSaving(null);
    }
  };

  const s = data?.summary;
  return (
    <>
      <PageHeader infoKey="financials" title="المدفوعات">
        <MonthInput value={month} onChange={setMonth} />
      </PageHeader>
      {error && <Banner tone="err">{error}</Banner>}
      {s && (
        <div className="dash-cards">
          <div className="dash-card">
            <div className="k">المتحصَّل</div>
            <div className="v">{fmtMoney(s.collected_total)}</div>
            <div className="stat-sub">
              {s.paid} من {s.students} دفعوا
            </div>
          </div>
          <div className="dash-card">
            <div className="k">المتبقي</div>
            <div className="v">{fmtMoney(s.outstanding_total)}</div>
            <div className="stat-sub">{s.unpaid} لم يدفعوا</div>
          </div>
          <div className="dash-card">
            <div className="k">المتوقع للشهر</div>
            <div className="v">{fmtMoney(s.expected_total)}</div>
            <div className="stat-sub">رسوم الصف × الطلاب النشطين</div>
          </div>
        </div>
      )}
      <div className="dash-filters">
        <div className="dash-search">
          <Search size={16} />
          <input
            placeholder="ابحث بالاسم"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <select className="inp" value={gradeId} onChange={(e) => setGradeId(e.target.value)}>
          <option value="">كل الصفوف</option>
          {grades.map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </select>
        <select className="inp" value={groupId} onChange={(e) => setGroupId(e.target.value)}>
          <option value="">كل المجموعات</option>
          {groups.map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </select>
        <select
          className="inp"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="">الكل</option>
          <option value="paid">المدفوع</option>
          <option value="unpaid">غير المدفوع</option>
        </select>
      </div>
      {!data && !error && <p className="field-msg">جاري تحميل البيانات...</p>}
      {data && data.rows.length === 0 && (
        <Empty title="لا توجد نتائج" text="لا يوجد طلاب نشطون مطابقون لهذه الاختيارات." />
      )}
      {data && data.rows.length > 0 && (
        <div className="dash-table-wrap">
          <table className="dash-table">
            <thead>
              <tr>
                <th>الطالب</th>
                <th>الصف</th>
                <th>قيمة الشهر</th>
                <th>الحالة</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <tr key={r.enrollment_id}>
                  <td>{r.name}</td>
                  <td>{r.grade}</td>
                  <td>{fmtMoney(r.amount)}</td>
                  <td>
                    <button
                      className={"dash-pill" + (r.status === "paid" ? " on" : "")}
                      disabled={saving === r.enrollment_id}
                      onClick={() => toggle(r)}
                      aria-label={r.status === "paid" ? "تحويل إلى غير مدفوع" : "تسجيل كمدفوع"}
                    >
                      {r.status === "paid" ? "مدفوع" : "غير مدفوع"}
                    </button>
                  </td>
                  <td>
                    <button className="mini-btn" onClick={() => setHistory(r)}>
                      <History size={13} /> السجل
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {history && <HistoryModal row={history} onClose={() => setHistory(null)} />}
    </>
  );
}

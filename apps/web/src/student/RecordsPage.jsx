import { useEffect, useState } from "react";
import { NotebookPen } from "lucide-react";
import { Banner, Btn, Modal } from "../auth/ui.jsx";
import { studentApi } from "../lib/studentApi.js";
import { ApiError } from "../lib/api.js";
import { PageHeader, Empty, fmtDate, fmtDateTime, fmtMonth } from "../dashboard/common.jsx";
import { STATE_LABEL, STATE_TONE, Stars } from "./HomePage.jsx";

const TABS = [
  ["attendance", "الحضور"],
  ["recitation", "التسميع"],
  ["payments", "الدفع"],
  ["evaluation", "التقييم"],
];
const LABEL = { present: "حاضر", absent: "غائب", studied: "ذاكر", not_studied: "لم يذاكر" };
const TONE = { present: "good", studied: "good", absent: "bad", not_studied: "bad" };

export default function RecordsPage() {
  const [tab, setTab] = useState("attendance");
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [receipt, setReceipt] = useState(null);
  useEffect(() => {
    setData(null);
    setErr(null);
    studentApi[tab]()
      .then(setData)
      .catch((e) => setErr(e instanceof ApiError ? e.message : "تعذّر تحميل السجل."));
  }, [tab]);

  return (
    <>
      <PageHeader infoKey="student_records" title="سجلّي">
        <div className="seg" role="tablist">
          {TABS.map(([k, l]) => (
            <button key={k} className={tab === k ? "active" : ""} onClick={() => setTab(k)}>
              {l}
            </button>
          ))}
        </div>
      </PageHeader>
      {err && <Banner tone="err">{err}</Banner>}
      {!data && !err && <p className="field-msg">جاري التحميل...</p>}
      {data && (tab === "attendance" || tab === "recitation") && (
        <>
          <div className="tag-list" style={{ marginBlockEnd: 12 }}>
            {Object.entries(data.summary).map(([k, n]) => (
              <span key={k} className={"chip-s " + TONE[k]}>
                {LABEL[k]}: {n}
              </span>
            ))}
          </div>
          {data.results.length === 0 ? (
            <Empty title="لا توجد سجلات بعد" text="ستظهر هنا بعد أن يسجّلها معلمك في الحصص." />
          ) : (
            <div className="list-rows">
              {data.results.map((r) => (
                <div key={r.id} className="list-row">
                  <div>
                    <strong>{r.group}</strong>
                    <div className="stat-sub">{fmtDate(r.date)}</div>
                  </div>
                  <span className={"chip-s " + TONE[r.status]}>{LABEL[r.status]}</span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
      {data && tab === "payments" && (
        <div className="list-rows">
          {data.results.map((r) => (
            <div key={r.month} className="list-row">
              <strong>{fmtMonth(r.month)}</strong>
              <span className="row-actions">
                <span className={"chip-s " + (r.status === "paid" ? "good" : "bad")}>
                  {r.status === "paid" ? "مدفوع" : "غير مدفوع"}
                </span>
                {r.receipt && (
                  <button className="mini-btn" onClick={() => setReceipt(r.receipt)}>
                    الإيصال
                  </button>
                )}
              </span>
            </div>
          ))}
        </div>
      )}
      {data &&
        tab === "evaluation" &&
        (data.results.length === 0 && !(data.notes || []).length ? (
          <Empty title="لا يوجد تقييم بعد" text="يظهر تقييمك الشهري هنا بعد أن ينشره معلمك." />
        ) : (
          <>
            <div className="list-rows">
              {data.results.map((r) => (
                <div key={r.month} className="list-row">
                  <strong>{fmtMonth(r.month)}</strong>
                  <span className="row-actions">
                    {r.state && (
                      <span className={"chip-s " + STATE_TONE[r.state]}>
                        {STATE_LABEL[r.state]}
                      </span>
                    )}
                    {r.rating ? (
                      <Stars value={r.rating} />
                    ) : (
                      <span className="stat-sub">التقييم لم يُنشر</span>
                    )}
                  </span>
                </div>
              ))}
            </div>

            {/* The teacher's written notes: what the state and the stars
                  actually mean, in the teacher's own words. */}
            {(data.notes || []).length > 0 && (
              <section className="eval-notes">
                <h3>
                  <NotebookPen size={15} /> ملاحظات معلّمك
                </h3>
                {data.notes.map((n) => (
                  <article key={n.id} className="eval-note">
                    <p>{n.body}</p>
                    <time className="stat-sub">{fmtDateTime(n.created_at)}</time>
                  </article>
                ))}
              </section>
            )}
          </>
        ))}

      {receipt && (
        <Modal
          size="md"
          title="إيصال سداد"
          text={`مرجع ${receipt.reference}`}
          onClose={() => setReceipt(null)}
          footer={
            <>
              <Btn variant="ghost" onClick={() => setReceipt(null)}>
                إغلاق
              </Btn>
              <Btn onClick={() => window.print()}>طباعة</Btn>
            </>
          }
        >
          <div className="invoice">
            <div className="invoice-head">
              <strong>{receipt.teacher_environment}</strong>
              <span className="stat-sub">إيصال سداد الرسوم الشهرية</span>
            </div>
            <dl className="invoice-rows">
              <div>
                <dt>الطالب</dt>
                <dd>{receipt.student_name}</dd>
              </div>
              <div>
                <dt>الصف</dt>
                <dd>{receipt.grade}</dd>
              </div>
              <div>
                <dt>المجموعة</dt>
                <dd>{receipt.groups?.join("، ") || "—"}</dd>
              </div>
              <div>
                <dt>عن شهر</dt>
                <dd>{fmtMonth(receipt.month)}</dd>
              </div>
              <div>
                <dt>تاريخ السداد</dt>
                <dd>{receipt.paid_at ? fmtDateTime(receipt.paid_at) : "—"}</dd>
              </div>
              <div>
                <dt>المرجع</dt>
                <dd>
                  <code>{receipt.reference}</code>
                </dd>
              </div>
            </dl>
            <div className="invoice-total">
              <span>المبلغ المدفوع</span>
              <strong>{receipt.amount}</strong>
            </div>
            {receipt.note && <p className="stat-sub">{receipt.note}</p>}
          </div>
        </Modal>
      )}
    </>
  );
}

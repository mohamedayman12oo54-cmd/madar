import { useState, useEffect } from "react";
import Reveal from "./Reveal.jsx";

const names = [
  "أحمد محمود",
  "سارة إبراهيم",
  "يوسف خالد",
  "ملك عادل",
  "عمر شريف",
  "ليلى حسن",
  "كريم سمير",
  "نور محمد",
  "حسن علي",
  "جنى وليد",
];
const TOTAL = 42;

function FastDemo() {
  const [idx, setIdx] = useState(0);
  const [pick, setPick] = useState({ att: null, rec: null });
  const [done, setDone] = useState(false);
  const [fade, setFade] = useState(false);

  useEffect(() => {
    if (pick.att && pick.rec) {
      const t = setTimeout(() => {
        if (idx + 1 >= TOTAL) {
          setDone(true);
          return;
        }
        setFade(true);
        setTimeout(() => {
          setIdx((i) => i + 1);
          setPick({ att: null, rec: null });
          setFade(false);
        }, 170);
      }, 240);
      return () => clearTimeout(t);
    }
  }, [pick, idx]);

  if (done) {
    return (
      <div className="fs-demo">
        <div className="fs-done">
          <div className="big">
            تمت معالجة <span className="num">42</span> طالبًا
          </div>
          <div className="fs-sum">
            <div>
              <div className="n">
                <span className="num">36</span>
              </div>
              <div className="l">حاضر</div>
            </div>
            <div>
              <div className="n">
                <span className="num">6</span>
              </div>
              <div className="l">غائب</div>
            </div>
            <div>
              <div className="n">
                <span className="num">29</span>
              </div>
              <div className="l">تم التسميع</div>
            </div>
            <div>
              <div className="n">
                <span className="num">9</span>
              </div>
              <div className="l">لم يتم</div>
            </div>
            <div>
              <div className="n">
                <span className="num">4</span>
              </div>
              <div className="l">تخطّي</div>
            </div>
          </div>
          <button
            className="btn btn-cream"
            style={{ marginInline: "auto" }}
            onClick={() => {
              setIdx(0);
              setPick({ att: null, rec: null });
              setDone(false);
            }}
          >
            إعادة المحاكاة
          </button>
          <div style={{ fontSize: ".8rem", color: "#AEB4C4", marginBlockStart: "14px" }}>
            السجلات محفوظة بالفعل — الإغلاق تحوّل في حالة الجلسة، لا حفظ جماعي.
          </div>
        </div>
      </div>
    );
  }

  const Opt = ({ k, v, label }) => (
    <button
      className={"opt" + (pick[k] === v ? " on" : "")}
      onClick={() => setPick((p) => ({ ...p, [k]: v }))}
    >
      {label}
    </button>
  );

  return (
    <div className="fs-demo">
      <div className="dh">
        <span>جلسة الصف الثالث — مجموعة الأحد</span>
        <span>
          الطالب <span className="num">{idx + 1}</span> من <span className="num">42</span>
        </span>
      </div>
      <div className="sname" style={{ opacity: fade ? 0 : 1 }}>
        {names[idx % names.length]}
      </div>
      <div className="ql">الحضور</div>
      <div className="opts">
        <Opt k="att" v="present" label="حاضر" />
        <Opt k="att" v="absent" label="غائب" />
      </div>
      <div className="ql">التسميع</div>
      <div className="opts">
        <Opt k="rec" v="studied" label="تم التسميع" />
        <Opt k="rec" v="not" label="لم يتم التسميع" />
        <Opt k="rec" v="skip" label="تخطّي" />
      </div>
      <div style={{ fontSize: ".85rem", color: "#AEB4C4", marginBlockStart: "6px" }}>
        <span className="num">{idx + 1}</span> / <span className="num">42</span>
      </div>
      <div className="fsbar">
        <i style={{ width: (((idx + 1) / TOTAL) * 100).toFixed(1) + "%" }} />
      </div>
    </div>
  );
}

export default function FastSessionSection() {
  return (
    <section className="section fs" id="fast-session">
      <div className="wrap fs-wrap">
        <Reveal>
          <div className="kicker">الجلسة السريعة</div>
          <h2 className="h2">سرعة، بلا تضحية بالدقة.</h2>
          <p className="lead">
            انقر الحضور، انقر التسميع، وانتقل فورًا للطالب التالي — بلا نوافذ ولا تأكيدات تعطّلك.
          </p>
          <div className="fs-note">
            <i />
            كل نقرة تُحفظ لحظتها، والإشعار يُعالَج لاحقًا دون أن يعطّلك. لا «حفظ جماعي» عند الإغلاق.
          </div>
        </Reveal>
        <Reveal delay={0.12}>
          <FastDemo />
        </Reveal>
      </div>
    </section>
  );
}

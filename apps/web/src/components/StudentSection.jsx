import { Check, MessageSquareText } from "lucide-react";
import Reveal from "./Reveal.jsx";
import { studentFeatures } from "../data/content";

export default function StudentSection() {
  return (
    <section className="section" id="students">
      <div className="wrap split">
        <Reveal aria-hidden="true">
          <div className="phone" aria-hidden="true">
            <div className="ph-top">
              <div className="ph-greet">مرحبًا، عمر<small>رحلتك التعليمية اليوم</small></div>
              <span className="chip">أ. أحمد</span>
            </div>
            <div className="ph-card"><div className="k">جلسة اليوم</div><div className="v">الرياضيات · <span className="num">4:00</span> م</div></div>
            <div className="ph2">
              <div className="ph-card"><div className="k">الحضور</div><div className="v">منتظم</div></div>
              <div className="ph-card"><div className="k">التسميع</div><div className="v">هذا الأسبوع</div></div>
            </div>
            <div className="asst">
              <div className="t"><MessageSquareText size={15} /> مساعد الدراسة الذكي</div>
              <span className="q">اشرح لي درس المعادلات</span>
            </div>
          </div>
        </Reveal>
        <Reveal delay={0.12}>
          <div className="kicker">للطلاب</div>
          <h2 className="h2">رحلتك التعليمية، أوضح.</h2>
          <p className="lead">تجربة للهاتف أولًا: حصص اليوم، والتقدّم، والاختبارات، والمحتوى — ومعلّم ذكي يجيب أسئلتك ضمن حدود مدار التعليمية.</p>
          <div className="feat">
            {studentFeatures.map((f, i) => (
              <div className="row" key={i}>
                <span className="fi"><Check size={13} /></span>
                <div><div className="ft">{f.t}</div><div className="fd">{f.d}</div></div>
              </div>
            ))}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

import { Check } from "lucide-react";
import Reveal from "./Reveal.jsx";
import { teacherFeatures } from "../data/content";

export default function TeacherSection() {
  return (
    <section className="section tint" id="teachers">
      <div className="wrap split">
        <Reveal>
          <div className="kicker">للمدرسين</div>
          <h2 className="h2">كل ما يحتاجه تدريسك. بلا ضجيج.</h2>
          <p className="lead">سريع أثناء الحصة، منظّم بعدها، وواضح حين تحتاج قرارًا.</p>
          <div className="feat">
            {teacherFeatures.map((f, i) => (
              <div className="row" key={i}>
                <span className="fi">
                  <Check size={13} />
                </span>
                <div>
                  <div className="ft">{f.t}</div>
                  <div className="fd">{f.d}</div>
                </div>
              </div>
            ))}
          </div>
        </Reveal>
        <Reveal delay={0.12}>
          <div className="mock" aria-hidden="true">
            <div className="mhead">
              <span>مساء الخير، أحمد</span>
              <small>
                الأحد · <span className="num">14</span> حصة
              </small>
            </div>
            <div className="mrow">
              <span className="who">
                <span className="ava" />
                جلسة الصف الثالث — <span className="num">4:00</span> م
              </span>
              <span className="tag">جاهزة</span>
            </div>
            <div className="mrow">
              <span className="who">
                <span className="ava" />
                مدفوعات متأخّرة
              </span>
              <span className="tag warn">
                <span className="num">8</span> طلاب
              </span>
            </div>
            <div className="mrow">
              <span className="who">
                <span className="ava" />
                طلاب يحتاجون متابعة
              </span>
              <span className="tag warn">
                <span className="num">3</span>
              </span>
            </div>
            <div className="barr">
              <i style={{ width: "76%" }} />
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

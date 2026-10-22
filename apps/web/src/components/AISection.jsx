import Reveal from "./Reveal.jsx";
import Icon from "./Icon.jsx";
import { aiCards } from "../data/content";

export default function AISection() {
  return (
    <section className="section" id="ai">
      <div className="wrap">
        <Reveal className="ai-head">
          <div className="kicker">الذكاء في مدار</div>
          <h2 className="h2">
            <span>ذكاء يساعدك…</span>
            <span>ولا يحلّ محلّك.</span>
          </h2>
          <p className="lead">
            يظهر الذكاء كطبقة هادئة داخل النظام — لا روبوت، ولا محادثة تطفو في كل مكان. يبقى
            استشاريًا، ولا يصبح مصدر الحقيقة.
          </p>
        </Reveal>
        <div className="ai-layer">
          {aiCards.map((c, i) => (
            <Reveal key={i} delay={i * 0.08}>
              <div className="ai-c">
                <div className="ic">
                  <Icon name={c.icon} size={18} />
                </div>
                <h3>{c.t}</h3>
                <p>{c.d}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

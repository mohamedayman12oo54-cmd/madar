import Reveal from "./Reveal.jsx";
import { steps } from "../data/content";

export default function HowItWorks() {
  return (
    <section className="section" id="how">
      <div className="wrap">
        <Reveal style={{ maxWidth: "40ch" }}>
          <div className="kicker">كيف يعمل مدار</div>
          <h2 className="h2">من بيئة فارغة إلى تدريس واضح.</h2>
        </Reveal>
        <div className="steps">
          {steps.map((s, i) => (
            <Reveal key={i} delay={i * 0.06}>
              <div className="stp">
                <span className="sn">{s.n}</span>
                <div><h3>{s.t}</h3><p>{s.d}</p></div>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

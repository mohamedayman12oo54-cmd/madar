import Reveal from "./Reveal.jsx";
import FeatureCard from "./FeatureCard.jsx";
import { features } from "../data/content";

export default function FeaturesSection() {
  return (
    <section className="section tint" id="features">
      <div className="wrap">
        <Reveal style={{ maxWidth: "38ch" }}>
          <div className="kicker">المميزات</div>
          <h2 className="h2">كل ما تحتاجه، في نظام واحد.</h2>
        </Reveal>
        <div className="fgrid">
          {features.map((f, i) => (
            <FeatureCard key={i} icon={f.icon} title={f.t} />
          ))}
        </div>
      </div>
    </section>
  );
}

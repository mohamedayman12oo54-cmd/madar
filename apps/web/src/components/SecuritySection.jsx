import { ShieldCheck, Users, Lock, Check } from "lucide-react";
import Reveal from "./Reveal.jsx";
import { security } from "../data/content";

const icons = [ShieldCheck, Users, Lock, Check];

export default function SecuritySection() {
  return (
    <section className="section sec" id="security">
      <div className="wrap sec-grid">
        <Reveal>
          <div className="kicker">الأمان والخصوصية</div>
          <h2 className="h2">بيانات كل مدرّس… تبقى في مدارها.</h2>
          <p className="lead">العزل ركيزة في مدار، لا إضافة لاحقة.</p>
        </Reveal>
        <Reveal delay={0.12}>
          <div className="sec-list">
            {security.map((s, i) => {
              const I = icons[i % icons.length];
              return (
                <div className="s" key={i}><I className="ic" size={18} /><span>{s}</span></div>
              );
            })}
          </div>
        </Reveal>
      </div>
    </section>
  );
}

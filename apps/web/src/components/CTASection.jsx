import { ArrowLeft } from "lucide-react";
import Reveal from "./Reveal.jsx";

export default function CTASection() {
  return (
    <section className="section final">
      <div className="wrap">
        <Reveal>
          <h2 className="h2">جاهز تخلّي التعليم يدور حول الطالب؟</h2>
          <p className="lead" style={{ marginInline: "auto" }}>ابدأ مع مدار — سريع، واضح، ومصمَّم بالعربية أولًا.</p>
          <div className="fcta">
            <a className="btn btn-primary btn-lg" href="#" onClick={(e) => e.preventDefault()}>ابدأ مع مدار <ArrowLeft className="arw" size={18} /></a>
            <a className="btn btn-ghost btn-lg" href="#intro">استكشف المنصة</a>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

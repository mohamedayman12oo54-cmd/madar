import { motion } from "framer-motion";
import { ArrowLeft } from "lucide-react";
import { heroStats } from "../data/content";

// The image carries the globe + "Madar/مدار" wordmark stacked in the centre.
// Copy is grouped into two balanced blocks that flank it: the message
// (heading + subtitle) on the right, and action + proof (CTA + stat chips,
// stacked) on the left — so neither side feels heavier or emptier than the
// other. Desktop: hero-visual is a full-bleed absolute layer (100vh cover).
// Phone (<=680px): a tall 100vh cover crops the wide image into an
// unreadable close-up, so hero-visual instead becomes a normal, fixed-
// aspect image band at the top, followed by clearly readable stacked copy
// below on solid cream — the layout most people will actually see.
export default function Hero({ ready }) {
  const t = (delay) => ({
    initial: { opacity: 0, y: 18 },
    animate: ready ? { opacity: 1, y: 0 } : { opacity: 0, y: 18 },
    transition: { duration: 0.9, ease: [0.16, 1, 0.3, 1], delay },
  });

  return (
    <header className="hero" id="top">
      <div className="hero-visual">
        <div
          className="hero-bg"
          style={{ backgroundImage: "url('/main.png')" }}
          aria-hidden="true"
        />
        <div className="hero-veil" aria-hidden="true" />
      </div>
      <div className="hero-inner">
        <div className="hero-flank">
          <motion.div className="hero-side hero-side-a" {...t(0.1)}>
            <h1>
              حيث يدور التعليم
              <br />
              حول الطالب.
            </h1>
            <p className="hero-sub">
              بيئة تعليمية واحدة تجمع المعلّم والطالب والحضور والتسميع والمدفوعات والتقييم — بوضوح،
              وبالعربية أولًا.
            </p>
          </motion.div>
          <motion.div className="hero-side hero-side-b" {...t(0.28)}>
            <div className="hero-stats">
              {heroStats.map((s, i) => (
                <div className="hero-chip" key={i}>
                  <div className="k">{s.k}</div>
                  <div className="l">{s.l}</div>
                </div>
              ))}
            </div>
            <div className="hero-cta">
              <a className="btn btn-primary" href="#intro">
                اكتشف مدار <ArrowLeft className="arw" size={18} />
              </a>
              <a className="btn btn-ghost" href="#how">
                كيف يعمل مدار؟
              </a>
            </div>
          </motion.div>
        </div>
      </div>
    </header>
  );
}

import { motion } from "framer-motion";
import logo from "../assets/madar-logo.png";

// Cinematic brand intro: reveal the lockup, hold, then travel toward the
// right edge as the landing page appears underneath (one continuous scene).
export default function LogoLoader() {
  const travel = typeof window !== "undefined" ? window.innerWidth * 0.32 : 320;
  return (
    <motion.div
      className="loader"
      initial={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.5 }}
    >
      <motion.div
        className="loader-logo"
        initial={{ opacity: 0, scale: 0.9, filter: "blur(10px)" }}
        animate={{
          opacity: [0, 1, 1, 0],
          scale: [0.9, 1, 1, 0.46],
          x: [0, 0, 0, travel],
          filter: ["blur(10px)", "blur(0px)", "blur(0px)", "blur(0px)"],
        }}
        transition={{ duration: 2.6, times: [0, 0.35, 0.72, 1], ease: [0.16, 1, 0.3, 1] }}
      >
        <img src={logo} alt="مدار — Madar" />
      </motion.div>
    </motion.div>
  );
}

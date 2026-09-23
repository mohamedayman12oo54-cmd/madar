import { motion } from "framer-motion";

export default function StatCard({ k, l, className = "", delay = 0 }) {
  return (
    <motion.div
      className={"stat " + className}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1], delay }}
    >
      <div className="k">{k}</div>
      <div className="l">{l}</div>
    </motion.div>
  );
}

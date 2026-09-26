// Phase 1 ships the dashboard SHELL — real per-section data (students,
// groups, sessions, ...) lands with their Phase 2+ backend endpoints. This
// is deliberately not fake data: no invented counts, tables, or charts.
import { Construction } from "lucide-react";

export default function ComingSoon({ title, text }) {
  return (
    <div className="dash-empty">
      <div className="ic"><Construction size={26} /></div>
      <h2>{title}</h2>
      <p>{text || "سيتم ربط هذا القسم بالبيانات الحقيقية عند اكتمال الجزء الخاص به من الواجهة الخلفية."}</p>
    </div>
  );
}

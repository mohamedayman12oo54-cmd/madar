import { parseSummary } from "../lib/summary.js";

/** Renders a teacher's summary. Every block is a React text node (auto-escaped): there is no HTML
 *  parsing anywhere, so stored text can never execute. */
export default function SummaryText({ text }) {
  const blocks = parseSummary(text);
  if (blocks.length === 0) return <p className="field-msg">لا يوجد نص.</p>;
  return (
    <div className="summary-text" dir="auto">
      {blocks.map((b, i) => {
        if (b.type === "h") return b.level === 1 ? <h3 key={i}>{b.text}</h3> : <h4 key={i}>{b.text}</h4>;
        if (b.type === "ul")
          return (
            <ul key={i}>
              {b.items.map((t, j) => (
                <li key={j}>{t}</li>
              ))}
            </ul>
          );
        if (b.type === "ol")
          return (
            <ol key={i}>
              {b.items.map((t, j) => (
                <li key={j}>{t}</li>
              ))}
            </ol>
          );
        return <p key={i}>{b.text}</p>;
      })}
    </div>
  );
}

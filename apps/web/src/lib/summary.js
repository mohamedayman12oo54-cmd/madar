// A teacher's written summary is PLAIN TEXT with light, line-based formatting. It is parsed into
// blocks here and rendered as React text nodes (components/SummaryText.jsx): it is never treated as
// HTML anywhere, so a summary cannot carry script, however it is written.
//
//   # عنوان كبير        -> heading (level 1)
//   ## عنوان فرعي       -> heading (level 2; deeper levels are folded into 2)
//   - نقطة  /  * نقطة  /  • نقطة   -> bullet list
//   1. خطوة  /  1) خطوة            -> numbered list
//   (blank line)          -> paragraph break
export const MAX_SUMMARY_CHARS = 20000;

const HEADING = /^(#{1,6})\s+(.+)$/;
const BULLET = /^\s*[-*•]\s+(.+)$/;
const NUMBERED = /^\s*\d+[.)]\s+(.+)$/;

export function parseSummary(text) {
  const blocks = [];
  let para = [];
  const flushPara = () => {
    if (para.length) blocks.push({ type: "p", text: para.join("\n") });
    para = [];
  };
  const pushItem = (type, item) => {
    flushPara();
    const last = blocks[blocks.length - 1];
    if (last && last.type === type) last.items.push(item);
    else blocks.push({ type, items: [item] });
  };

  for (const raw of String(text ?? "").replace(/\r\n?/g, "\n").split("\n")) {
    const line = raw.replace(/\s+$/, "");
    if (!line.trim()) {
      flushPara();
      continue;
    }
    let m;
    if ((m = line.trim().match(HEADING))) {
      flushPara();
      blocks.push({ type: "h", level: m[1].length === 1 ? 1 : 2, text: m[2].trim() });
    } else if ((m = line.match(BULLET))) pushItem("ul", m[1].trim());
    else if ((m = line.match(NUMBERED))) pushItem("ol", m[1].trim());
    else para.push(line.trim());
  }
  flushPara();
  return blocks;
}

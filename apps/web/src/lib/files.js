// Human-readable file sizes in Arabic ("٢٫١ ميجابايت"), used by the teacher form and the student cards.
export function formatBytes(bytes) {
  const n = Number(bytes);
  if (!Number.isFinite(n) || n <= 0) return "";
  const num = (v, digits) => v.toLocaleString("ar-EG", { maximumFractionDigits: digits });
  if (n < 1024 * 1024) return `${num(Math.max(1, Math.round(n / 1024)), 0)} كيلوبايت`;
  return `${num(n / (1024 * 1024), 1)} ميجابايت`;
}

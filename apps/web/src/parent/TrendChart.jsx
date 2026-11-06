import { useState } from "react";
import { fmtMonth } from "../lib/dates.js";
import "./trend.css";

// Two measures on ONE axis (both are percentages). The 1-5 rating is a different scale, so it is a row of
// numbers under the chart, never a second axis.
const W = 360;
const H = 206;
const M = { l: 34, r: 18, t: 26, b: 52 };
const SERIES = [
  { key: "attendance_percent", name: "الحضور", cls: "s1", shape: "circle" },
  { key: "exam_percent", name: "الامتحانات", cls: "s2", shape: "square" },
];

const x = (i, n) => M.l + (n === 1 ? (W - M.l - M.r) / 2 : (i * (W - M.l - M.r)) / (n - 1));
const y = (v) => M.t + ((100 - v) * (H - M.t - M.b)) / 100;
const fmt = (v) => (Number.isInteger(v) ? String(v) : String(Math.round(v * 10) / 10));

/** A line is drawn in runs: a month without data breaks it rather than being bridged by a made-up line. */
function runs(points) {
  const out = [];
  let cur = [];
  for (const p of points) {
    if (p.v == null) {
      if (cur.length) out.push(cur);
      cur = [];
    } else cur.push(p);
  }
  if (cur.length) out.push(cur);
  return out;
}

function Marker({ shape, cx, cy, cls }) {
  return shape === "square" ? (
    <rect className={"tc-dot " + cls} x={cx - 4.5} y={cy - 4.5} width={9} height={9} rx={1.5} />
  ) : (
    <circle className={"tc-dot " + cls} cx={cx} cy={cy} r={4.5} />
  );
}

/** Month-by-month attendance % and exam average %, with the published rating alongside.
 *  Hover or focus a month for the exact figures; "عرض كجدول" shows the same data as a table. */
export default function TrendChart({ trend }) {
  const [at, setAt] = useState(null);
  const [table, setTable] = useState(false);
  const n = trend.length;
  const has = trend.some((m) => m.attendance_percent != null || m.exam_percent != null);
  const hasRating = trend.some((m) => m.rating != null);
  if (!has && !hasRating) return <p className="field-msg">لا توجد بيانات كافية بعد.</p>;

  const lines = SERIES.map((s) => ({ ...s, pts: trend.map((m, i) => ({ i, v: m[s.key] })) }));
  const hovered = at != null ? trend[at] : null;

  return (
    <div className="tc">
      <div className="tc-head">
        <ul className="tc-legend" aria-label="دليل الألوان">
          {SERIES.map((s) => (
            <li key={s.key}>
              <svg width="22" height="10" aria-hidden="true">
                <line className={"tc-key " + s.cls} x1="1" y1="5" x2="21" y2="5" />
              </svg>
              {s.name} %
            </li>
          ))}
        </ul>
        <button type="button" className="mini-btn" onClick={() => setTable((t) => !t)} aria-pressed={table}>
          {table ? "عرض كرسم" : "عرض كجدول"}
        </button>
      </div>

      {table ? (
        <div className="dash-table-wrap">
          <table className="dash-table">
            <thead>
              <tr>
                <th>الشهر</th>
                <th>الحضور %</th>
                <th>الامتحانات %</th>
                <th>التقييم</th>
              </tr>
            </thead>
            <tbody>
              {trend.map((m) => (
                <tr key={m.month}>
                  <td>{fmtMonth(m.month)}</td>
                  <td>{m.attendance_percent != null ? fmt(m.attendance_percent) : "—"}</td>
                  <td>{m.exam_percent != null ? fmt(m.exam_percent) : "—"}</td>
                  <td>{m.rating != null ? `${m.rating} / 5` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="tc-plot" dir="ltr" onMouseLeave={() => setAt(null)}>
          <svg
            viewBox={`0 0 ${W} ${H}`}
            role="img"
            aria-label="تطور نسبة الحضور ومتوسط الامتحانات خلال الأشهر الستة الأخيرة"
          >
            {[0, 50, 100].map((g) => (
              <g key={g}>
                <line className="tc-grid" x1={M.l} x2={W - M.r} y1={y(g)} y2={y(g)} />
                <text className="tc-tick" x={M.l - 6} y={y(g) + 3} textAnchor="end">
                  {g}
                </text>
              </g>
            ))}
            {trend.map((m, i) => (
              <text key={m.month} className="tc-tick" x={x(i, n)} y={H - 32} textAnchor="middle">
                {m.month.slice(5)}
              </text>
            ))}
            {hasRating && (
              <g aria-label="التقييم الشهري المنشور">
                <line className="tc-grid" x1={M.l} x2={W - M.r} y1={H - 24} y2={H - 24} />
                {trend.map((m, i) => (
                  <text key={m.month} className="tc-rate" x={x(i, n)} y={H - 7} textAnchor="middle">
                    {m.rating != null ? `★ ${m.rating}` : "—"}
                  </text>
                ))}
              </g>
            )}
            {at != null && <line className="tc-cross" x1={x(at, n)} x2={x(at, n)} y1={M.t} y2={H - M.b} />}
            {lines.map((s) =>
              runs(s.pts).map((r) => (
                <polyline
                  key={s.key + r[0].i}
                  className={"tc-line " + s.cls}
                  points={r.map((p) => `${x(p.i, n)},${y(p.v)}`).join(" ")}
                />
              ))
            )}
            {lines.map((s) =>
              s.pts
                .filter((p) => p.v != null)
                .map((p) => <Marker key={s.key + p.i} shape={s.shape} cls={s.cls} cx={x(p.i, n)} cy={y(p.v)} />)
            )}
            {/* The latest value of each series, printed on the chart in ink (never the series colour). The
                higher one sits above its point and the lower one below, so two close values do not collide. */}
            {(() => {
              const last = lines
                .map((s) => ({ s, p: [...s.pts].reverse().find((q) => q.v != null) }))
                .filter((l) => l.p);
              const top = last.length > 1 ? Math.max(...last.map((l) => l.p.v)) : null;
              return last.map(({ s, p }) => (
                <text
                  key={s.key}
                  className="tc-val"
                  x={x(p.i, n)}
                  y={y(p.v) + (top != null && p.v < top ? 16 : -9)}
                  textAnchor="middle"
                >
                  {fmt(p.v)}%
                </text>
              ));
            })()}
            {/* Wide invisible columns: the pointer or keyboard only has to be near a month. */}
            {trend.map((m, i) => (
              <rect
                key={m.month}
                className="tc-hit"
                x={x(i, n) - (W - M.l - M.r) / (2 * Math.max(n - 1, 1))}
                y={M.t}
                width={(W - M.l - M.r) / Math.max(n - 1, 1)}
                height={H - M.t - M.b}
                tabIndex={0}
                aria-label={`${fmtMonth(m.month)}: الحضور ${m.attendance_percent ?? "لا بيانات"}، الامتحانات ${m.exam_percent ?? "لا بيانات"}`}
                onMouseEnter={() => setAt(i)}
                onFocus={() => setAt(i)}
                onBlur={() => setAt(null)}
              />
            ))}
          </svg>
          {hovered && (
            <div
              className="tc-tip"
              style={{ left: `${(x(at, n) / W) * 100}%` }}
              dir="rtl"
              role="status"
            >
              <div className="tc-tip-month">{fmtMonth(hovered.month)}</div>
              {SERIES.map((s) => (
                <div key={s.key} className="tc-tip-row">
                  <svg width="14" height="8" aria-hidden="true">
                    <line className={"tc-key " + s.cls} x1="1" y1="4" x2="13" y2="4" />
                  </svg>
                  <strong>{hovered[s.key] != null ? `${fmt(hovered[s.key])}%` : "—"}</strong>
                  <span>{s.name}</span>
                </div>
              ))}
              {hovered.rating != null && (
                <div className="tc-tip-row">
                  <strong>★ {hovered.rating}</strong>
                  <span>التقييم</span>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Shared building blocks of the Control Center: data hook, permission context, toasts, page head, table, filters,
// states and the (dependency-free) charts. Everything draws only what the API returned.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  ChevronLeft,
  ChevronRight,
  Inbox,
  Minus,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { Btn, Modal } from "../auth/ui.jsx";
import { fmtDateTime } from "../lib/dates.js";

export { fmtDateTime };

/* ------------------------------------------------------------------ permissions + toasts */
const CC = createContext(null);
export const useControl = () => useContext(CC);
export const useCan = () => {
  const { permissions } = useContext(CC);
  return useCallback((...keys) => keys.some((k) => permissions.includes(k)), [permissions]);
};

export function ControlProvider({ me, children }) {
  const [toasts, setToasts] = useState([]);
  const toast = useCallback((text, tone = "ok") => {
    const id = Math.random().toString(36).slice(2);
    setToasts((t) => [...t, { id, text, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === "err" ? 6500 : 3800);
  }, []);
  const value = useMemo(() => ({ me, permissions: me.permissions, toast }), [me, toast]);
  return (
    <CC.Provider value={value}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={"toast" + (t.tone === "err" ? " err" : "")}>
            {t.text}
          </div>
        ))}
      </div>
    </CC.Provider>
  );
}
export const useToast = () => useContext(CC).toast;

/* ------------------------------------------------------------------ data */
/** Loads `fn()` whenever `deps` change. Late answers of an older request never overwrite a newer one. */
export function useApi(fn, deps = [], { skip = false } = {}) {
  const [state, setState] = useState({ loading: !skip, data: null, error: null });
  const seq = useRef(0);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const run = useCallback(() => {
    const id = ++seq.current;
    setState((s) => ({ ...s, loading: true, error: null }));
    fnRef
      .current()
      .then((data) => id === seq.current && setState({ loading: false, data, error: null }))
      .catch((error) => id === seq.current && setState((s) => ({ ...s, loading: false, error })));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!skip) run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [skip, ...deps]);
  return { ...state, reload: run };
}

export function errText(e, fallback = "حدث خطأ غير متوقع.") {
  if (!e) return fallback;
  if (!e.status) {
    // fetch() rejects with a TypeError when the network is down; any other status-less Error is OUR validation message
    return e.name === "TypeError" ? "تعذّر الاتصال بالخادم. تحقق من الاتصال وحاول مرة أخرى." : e.message || fallback;
  }
  if (e.status === 403) return "ليس لديك صلاحية لهذا الإجراء.";
  if (e.status >= 500) return "حدث خطأ في الخادم. حاول لاحقًا.";
  const f = e.fields;
  if (f && typeof f === "object") {
    const first = Object.values(f).flat()[0];
    if (typeof first === "string") return first;
  }
  return e.message || fallback;
}
/** Field errors from a 400 as {field: "message"} for <Field error=…>. */
export function fieldErrors(e) {
  const out = {};
  if (e?.fields && typeof e.fields === "object" && !Array.isArray(e.fields)) {
    for (const [k, v] of Object.entries(e.fields)) out[k] = Array.isArray(v) ? v[0] : String(v);
  }
  return out;
}

/** Runs an action with a busy flag and success/error toasts. Ignores a second click while one is running. */
export function useAction() {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const run = useCallback(
    async (fn, ok) => {
      if (busyRef.current) return undefined;
      busyRef.current = true;
      setBusy(true);
      try {
        const r = await fn();
        if (r === false) return undefined; // the action refused to run (client-side validation): no success toast
        if (ok) toast(ok);
        return r ?? true;
      } catch (e) {
        toast(errText(e), "err");
        return undefined;
      } finally {
        busyRef.current = false;
        setBusy(false);
      }
    },
    [toast]
  );
  return [run, busy];
}

export const useDebounce = (value, ms = 350) => {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
};

/** URL-less filter state with automatic page reset. */
export function useFilters(initial) {
  const [f, setF] = useState({ page: 1, ...initial });
  const set = useCallback((patch) => setF((p) => ({ ...p, page: 1, ...patch })), []);
  const setPage = useCallback((page) => setF((p) => ({ ...p, page })), []);
  return [f, set, setPage];
}

/** The API hands back in-app links such as "/team/support/tickets/5". They are re-rooted under a fixed "/team/"
 *  prefix at the call site (`to={`/team/${teamRel(link)}`}`), so a link can never send the browser elsewhere. */
export const teamRel = (link) => String(link || "").replace(/^\/?team\/?/, "").replace(/^\/+/, "");

/* ------------------------------------------------------------------ formatting */
const nf = new Intl.NumberFormat("en-US");
export const num = (v) => (v === null || v === undefined ? "—" : nf.format(v));
export const money = (v, cur = "EGP") =>
  v === null || v === undefined ? "—" : `${new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(v)} ${cur === "EGP" ? "ج.م" : cur}`;
export const hoursText = (h) => {
  if (h === null || h === undefined) return "—";
  if (h < 1) return `${nf.format(Math.round(h * 60))} د`;
  if (h < 48) return `${nf.format(Math.round(h * 10) / 10)} س`;
  return `${nf.format(Math.round(h / 24))} يوم`;
};
export const secsText = (s) => (s === null || s === undefined ? "—" : s < 60 ? `${nf.format(s)} ث` : `${nf.format(Math.round(s / 6) / 10)} د`);
export const msText = (ms) => (ms === null || ms === undefined ? "—" : ms < 1000 ? `${nf.format(ms)} ملّي ث` : `${nf.format(Math.round(ms / 100) / 10)} ث`);
const dtFmt = new Intl.DateTimeFormat("ar-EG-u-nu-latn", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" });
export const dt = (v) => (v ? dtFmt.format(new Date(v)) : "—");
const rtf = new Intl.RelativeTimeFormat("ar-u-nu-latn", { numeric: "auto" });
export function ago(v) {
  if (!v) return "—";
  const s = (new Date(v).getTime() - Date.now()) / 1000;
  const a = Math.abs(s);
  if (a < 60) return "الآن";
  if (a < 3600) return rtf.format(Math.round(s / 60), "minute");
  if (a < 86400) return rtf.format(Math.round(s / 3600), "hour");
  return rtf.format(Math.round(s / 86400), "day");
}
const dayFmt = new Intl.DateTimeFormat("ar-EG-u-nu-latn", { day: "numeric", month: "short" });
export const shortDay = (iso) => dayFmt.format(new Date(iso + "T12:00:00"));

/* ------------------------------------------------------------------ layout */
export function PageHead({ title, desc, crumbs = [], children }) {
  return (
    <>
      {crumbs.length > 0 && (
        <nav className="cc-crumbs" aria-label="مسار التنقل">
          <Link to="/team">مدار</Link>
          {crumbs.map(({ label, to }, i) => (
            <span key={i}>
              <ChevronLeft size={13} aria-hidden="true" style={{ verticalAlign: "-2px" }} />{" "}
              {to ? <Link to={to}>{label}</Link> : <span aria-current="page">{label}</span>}
            </span>
          ))}
        </nav>
      )}
      <div className="cc-head">
        <div>
          <h1>{title}</h1>
          {desc && <p>{desc}</p>}
        </div>
        {children && <div className="cc-actions">{children}</div>}
      </div>
    </>
  );
}

export function Card({ title, sub, actions, children, pad = true, className = "" }) {
  return (
    <section className={"cc-card " + className}>
      {(title || actions) && (
        <header>
          <div>
            {title && <h2>{title}</h2>}
            {sub && <div className="sub">{sub}</div>}
          </div>
          {actions}
        </header>
      )}
      {pad ? <div className="pad">{children}</div> : children}
    </section>
  );
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="cc-tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.key} role="tab" aria-selected={value === t.key} className={value === t.key ? "on" : ""} onClick={() => onChange(t.key)}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Badge({ tone = "plain", children, className = "" }) {
  return <span className={`cc-badge ${tone} ${className}`}>{children}</span>;
}
export const StatusBadge = ({ map, value }) => {
  const [label, tone] = map[value] || [value, "plain"];
  return <Badge tone={tone}>{label}</Badge>;
};
export const PriorityBadge = ({ value, labels }) => <Badge className={"pri-" + value + " plain"}>{labels[value] || value}</Badge>;

/* ------------------------------------------------------------------ states */
export function Skeleton({ rows = 5 }) {
  return (
    <div className="pad" aria-busy="true" aria-label="جارٍ التحميل" style={{ display: "grid", gap: 14 }}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skel" style={{ width: `${95 - ((i * 13) % 40)}%`, height: 16 }} />
      ))}
    </div>
  );
}
export function EmptyState({ title = "لا توجد نتائج", text, icon: Icon = Inbox }) {
  return (
    <div className="cc-state">
      <span className="ic">
        <Icon size={22} />
      </span>
      <h3>{title}</h3>
      {text && <p>{text}</p>}
    </div>
  );
}
export function ErrorState({ error, onRetry }) {
  return (
    <div className="cc-state err" role="alert">
      <span className="ic">
        <AlertTriangle size={22} />
      </span>
      <h3>{error?.status === 403 ? "لا تملك الصلاحية" : "تعذّر تحميل البيانات"}</h3>
      <p>{errText(error)}</p>
      {onRetry && error?.status !== 403 && (
        <Btn variant="secondary" onClick={onRetry}>
          إعادة المحاولة
        </Btn>
      )}
    </div>
  );
}
/** Standard wrapper: skeleton while loading the first time, error with retry, else children(data). */
export function Async({ api, children, rows }) {
  if (api.error && !api.data) return <ErrorState error={api.error} onRetry={api.reload} />;
  if (!api.data) return <Skeleton rows={rows} />;
  return children(api.data);
}

export function Confirm({ title, text, confirmLabel = "تأكيد", danger, onConfirm, onClose, children }) {
  const [busy, setBusy] = useState(false);
  return (
    <Modal
      title={title}
      text={text}
      onClose={busy ? undefined : onClose}
      footer={
        <>
          <Btn variant="ghost" onClick={onClose} disabled={busy}>
            إلغاء
          </Btn>
          <Btn
            variant={danger ? "danger" : "primary"}
            loading={busy}
            loadingText="جارٍ التنفيذ…"
            onClick={async () => {
              setBusy(true);
              try {
                const ok = await onConfirm();
                if (ok !== false) onClose();
              } finally {
                setBusy(false);
              }
            }}
          >
            {confirmLabel}
          </Btn>
        </>
      }
    >
      {children}
    </Modal>
  );
}

/* ------------------------------------------------------------------ controls */
export function Select({ label, value, onChange, options, all = "الكل", ...p }) {
  const el = (
    <select className="cc-select" value={value ?? ""} onChange={(e) => onChange(e.target.value)} {...p}>
      {all !== null && <option value="">{all}</option>}
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
  return label ? (
    <label className="cc-field">
      <span>{label}</span>
      {el}
    </label>
  ) : (
    el
  );
}
export const opts = (obj) => Object.entries(obj).map(([value, v]) => ({ value, label: Array.isArray(v) ? v[0] : v }));

export function SearchBox({ value, onChange, placeholder = "بحث…" }) {
  return (
    <input
      type="search"
      className="cc-input search"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      aria-label={placeholder}
    />
  );
}
export function TextArea(props) {
  return <textarea className="cc-textarea" {...props} />;
}
export function Input(props) {
  return <input className="cc-input" style={{ width: "100%" }} {...props} />;
}

export const RANGES = [
  { value: "today", label: "اليوم" },
  { value: "7d", label: "آخر 7 أيام" },
  { value: "30d", label: "آخر 30 يومًا" },
  { value: "90d", label: "آخر 90 يومًا" },
  { value: "custom", label: "نطاق مخصص" },
];
/** Date-range control; `value` = {range, from, to}. Custom needs both dates before it is applied. */
export function RangePicker({ value, onChange }) {
  const [draft, setDraft] = useState({ from: value.from || "", to: value.to || "" });
  const custom = value.range === "custom";
  const apply = (patch) => {
    const next = { ...draft, ...patch };
    setDraft(next);
    if (next.from && next.to && next.from <= next.to) onChange({ range: "custom", ...next });
  };
  return (
    <div className="cc-actions">
      <Select
        value={value.range}
        all={null}
        options={RANGES}
        aria-label="الفترة"
        onChange={(r) => (r === "custom" ? onChange({ range: "custom", from: draft.from, to: draft.to }) : onChange({ range: r }))}
      />
      {custom && (
        <>
          <input type="date" className="cc-input" aria-label="من" value={draft.from} max={draft.to || undefined} onChange={(e) => apply({ from: e.target.value })} />
          <input type="date" className="cc-input" aria-label="إلى" value={draft.to} min={draft.from || undefined} onChange={(e) => apply({ to: e.target.value })} />
        </>
      )}
    </div>
  );
}
export const rangeParams = (r) => (r.range === "custom" ? (r.from && r.to ? r : { range: "30d" }) : { range: r.range });

/* ------------------------------------------------------------------ table */
export function Pager({ page, pages, count, onPage }) {
  return (
    <div className="pager">
      <span>
        {num(count)} نتيجة · صفحة {num(page)} من {num(pages)}
      </span>
      <span style={{ display: "flex", gap: 6 }}>
        <Btn variant="secondary" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="الصفحة السابقة">
          <ChevronRight size={16} /> السابق
        </Btn>
        <Btn variant="secondary" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label="الصفحة التالية">
          التالي <ChevronLeft size={16} />
        </Btn>
      </span>
    </div>
  );
}

/** columns: [{key,label,render?(row),sort?:"field",className?,ltr?}]  — `sort` ({key,dir}) + `onSort` for server sorting. */
export function DataTable({ columns, rows, rowKey = "id", onRow, sort, onSort, selected, onSelect, empty }) {
  const selectable = Boolean(onSelect);
  const allOn = selectable && rows.length > 0 && rows.every((r) => selected?.includes(r[rowKey]));
  if (rows.length === 0) return empty || <EmptyState />;
  return (
    <div className="tbl-wrap">
      <table className="tbl stack">
        <thead>
          <tr>
            {selectable && (
              <th className="sel">
                <input
                  type="checkbox"
                  aria-label="تحديد الكل"
                  checked={allOn}
                  onChange={() => onSelect(allOn ? [] : rows.map((r) => r[rowKey]))}
                />
              </th>
            )}
            {columns.map((c) => (
              <th key={c.key} aria-sort={c.sort && sort?.key === c.sort ? (sort.dir === "asc" ? "ascending" : "descending") : undefined}>
                {c.sort && onSort ? (
                  <button onClick={() => onSort(c.sort)}>
                    {c.label}
                    {sort?.key === c.sort && (sort.dir === "asc" ? <ArrowUp size={13} /> : <ArrowDown size={13} />)}
                  </button>
                ) : (
                  c.label
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={r[rowKey]}
              className={onRow ? "click" : ""}
              onClick={onRow ? () => onRow(r) : undefined}
              tabIndex={onRow ? 0 : undefined}
              onKeyDown={onRow ? (e) => e.key === "Enter" && onRow(r) : undefined}
            >
              {selectable && (
                <td className="sel" onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox"
                    aria-label="تحديد الصف"
                    checked={selected?.includes(r[rowKey]) || false}
                    onChange={() =>
                      onSelect(selected?.includes(r[rowKey]) ? selected.filter((x) => x !== r[rowKey]) : [...(selected || []), r[rowKey]])
                    }
                  />
                </td>
              )}
              {columns.map((c) => (
                <td key={c.key} data-label={c.label} className={(c.className || "") + (c.ltr ? " ltr" : "")}>
                  {c.render ? c.render(r) : r[c.key] ?? "—"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
/** `sort` state helper: click toggles direction, a new key starts descending. */
export function useSort(initial) {
  const [sort, setSort] = useState(initial);
  const toggle = useCallback((key) => setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "desc" })), []);
  return [sort, toggle, sort.dir === "desc" ? "-" + sort.key : sort.key];
}

export function Trend({ pct, goodWhenDown = false }) {
  if (pct === null || pct === undefined) return <span className="trend flat"><Minus size={13} /> جديد</span>;
  if (pct === 0) return <span className="trend flat"><Minus size={13} /> 0%</span>;
  const up = pct > 0;
  const good = goodWhenDown ? !up : up;
  const I = up ? TrendingUp : TrendingDown;
  return (
    <span className={"trend " + (good ? "up" : "down")}>
      <I size={14} /> {num(Math.abs(pct))}%
    </span>
  );
}

export function KV({ items }) {
  return (
    <dl className="kv">
      {items.filter(Boolean).map(([k, v]) => (
        <div key={k} style={{ display: "contents" }}>
          <dt>{k}</dt>
          <dd>{v ?? "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

/* ------------------------------------------------------------------ charts */
export const SERIES = { navy: "#313851", c1: "#2a78d6", c2: "#eb6834", c3: "#1baf7a", c4: "#eda100" };
const H = 240;
const PAD = { t: 14, r: 14, b: 30, l: 44 };

function niceMax(v) {
  if (v <= 4) return 4;
  const raw = v / 4;
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 5, 10].map((m) => m * p).find((x) => x >= raw);
  return step * 4;
}

/** Real pixel width of a container, so chart text is drawn at its true size instead of being scaled with the SVG. */
function useWidth(fallback = 640) {
  const ref = useRef(null);
  const [w, setW] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(([e]) => setW(Math.max(260, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

/** A chart plus a "view as table" switch, so values are never colour-only or hover-only. */
export function ChartCard({ title, sub, legend, table, children }) {
  const [asTable, setAsTable] = useState(false);
  return (
    <Card
      title={title}
      sub={sub}
      pad={false}
      actions={
        table ? (
          <button type="button" className="view-toggle" onClick={() => setAsTable((v) => !v)} aria-pressed={asTable}>
            {asTable ? "عرض الرسم" : "عرض كجدول"}
          </button>
        ) : null
      }
    >
      {legend && legend.length > 1 && !asTable && (
        <div className="legend">
          {legend.map((l) => (
            <span key={l.label}>
              <i style={{ background: l.color }} />
              {l.label}
            </span>
          ))}
        </div>
      )}
      <div className="pad">
        {asTable && table ? (
          <div className="tbl-wrap" style={{ maxHeight: 260, overflow: "auto" }}>
            <table className="tbl">
              <thead>
                <tr>
                  {table.columns.map((c) => (
                    <th key={c}>{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.rows.map((r, i) => (
                  <tr key={i}>
                    {r.map((c, j) => (
                      <td key={j} className="cc-num">
                        {c}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          children
        )}
      </div>
    </Card>
  );
}

/** series: [{label,color,points:[{date,value}]}] — one shared x axis, crosshair tooltip. `area` fills a single series. */
export function LineChart({ series, area = false, height = H, format = num }) {
  const [hover, setHover] = useState(null);
  const [ref, W] = useWidth();
  const pts = series[0]?.points || [];
  const n = pts.length;
  const max = niceMax(Math.max(1, ...series.flatMap((s) => s.points.map((p) => p.value))));
  const iw = W - PAD.l - PAD.r;
  const ih = height - PAD.t - PAD.b;
  const x = (i) => PAD.l + (n <= 1 ? iw / 2 : (i * iw) / (n - 1));
  const y = (v) => PAD.t + ih - (v / max) * ih;
  const ticks = [0, 1, 2, 3, 4].map((i) => (max * i) / 4);
  const xt = n <= 8 ? pts.map((_, i) => i) : [0, Math.floor(n / 4), Math.floor(n / 2), Math.floor((3 * n) / 4), n - 1];
  const move = (e) => {
    const r = ref.current.getBoundingClientRect();
    const rel = (e.clientX - r.left) / r.width;
    const px = rel * W;
    const i = n <= 1 ? 0 : Math.round(((px - PAD.l) / iw) * (n - 1));
    setHover(Math.max(0, Math.min(n - 1, i)));
  };
  if (n === 0) return <EmptyState title="لا توجد بيانات في هذه الفترة" />;
  return (
    <div className="chart" ref={ref} onPointerMove={move} onPointerLeave={() => setHover(null)}>
      <svg viewBox={`0 0 ${W} ${height}`} role="img" aria-label={series.map((s) => s.label).join("، ")}>
        <g className="grid">
          {ticks.map((t) => (
            <line key={t} x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} />
          ))}
        </g>
        <g className="axis">
          {ticks.map((t) => (
            <text key={t} x={PAD.l - 6} y={y(t) + 4} textAnchor="end">
              {num(Math.round(t * 10) / 10)}
            </text>
          ))}
          {xt.map((i) => (
            <text key={i} x={x(i)} y={height - 6} textAnchor="middle">
              {shortDay(pts[i].date)}
            </text>
          ))}
        </g>
        {series.map((s, si) => {
          const d = s.points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(" ");
          return (
            <g key={s.label}>
              {area && si === 0 && <path d={`${d} L${x(n - 1)},${y(0)} L${x(0)},${y(0)} Z`} fill={s.color} opacity="0.12" />}
              <path d={d} fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
              {n <= 31 && s.points.map((p, i) => <circle key={i} cx={x(i)} cy={y(p.value)} r="2.5" fill={s.color} />)}
            </g>
          );
        })}
        {hover !== null && (
          <g>
            <line x1={x(hover)} x2={x(hover)} y1={PAD.t} y2={PAD.t + ih} stroke="#313851" strokeOpacity="0.35" strokeDasharray="3 3" />
            {series.map((s) => (
              <circle key={s.label} cx={x(hover)} cy={y(s.points[hover].value)} r="5" fill={s.color} stroke="#fff" strokeWidth="2" />
            ))}
          </g>
        )}
      </svg>
      {hover !== null && (
        <div className="tip" style={{ left: `${(x(hover) / W) * 100}%`, top: 0 }}>
          <b>{shortDay(pts[hover].date)}</b>
          {series.map((s) => (
            <div key={s.label}>
              <span>
                <i style={{ display: "inline-block", width: 8, height: 8, borderRadius: 2, background: s.color, marginInlineEnd: 6 }} />
                {s.label}
              </span>
              <b style={{ margin: 0 }}>{format(s.points[hover].value)}</b>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Vertical bars for one or two series (grouped), per-bar tooltip. */
export function BarChart({ series, height = H, format = num }) {
  const [hover, setHover] = useState(null);
  const [wrapRef, W] = useWidth();
  const pts = series[0]?.points || [];
  const n = pts.length;
  const max = niceMax(Math.max(1, ...series.flatMap((s) => s.points.map((p) => p.value))));
  const iw = W - PAD.l - PAD.r;
  const ih = height - PAD.t - PAD.b;
  const slot = iw / Math.max(n, 1);
  const bw = Math.max(2, Math.min(28, (slot - 4) / series.length - 2));
  const ticks = [0, 1, 2, 3, 4].map((i) => (max * i) / 4);
  const y = (v) => PAD.t + ih - (v / max) * ih;
  const step = Math.ceil(n / 8);
  if (n === 0) return <EmptyState title="لا توجد بيانات في هذه الفترة" />;
  return (
    <div className="chart" ref={wrapRef} onPointerLeave={() => setHover(null)}>
      <svg viewBox={`0 0 ${W} ${height}`} role="img" aria-label={series.map((s) => s.label).join("، ")}>
        <g className="grid">
          {ticks.map((t) => (
            <line key={t} x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} />
          ))}
        </g>
        <g className="axis">
          {ticks.map((t) => (
            <text key={t} x={PAD.l - 6} y={y(t) + 4} textAnchor="end">
              {num(Math.round(t * 10) / 10)}
            </text>
          ))}
          {pts.map((p, i) =>
            i % step === 0 ? (
              <text key={i} x={PAD.l + slot * i + slot / 2} y={height - 6} textAnchor="middle">
                {shortDay(p.date)}
              </text>
            ) : null
          )}
        </g>
        {pts.map((p, i) => (
          <g key={i} onPointerEnter={() => setHover(i)}>
            <rect x={PAD.l + slot * i} y={PAD.t} width={slot} height={ih} fill={hover === i ? "rgba(49,56,81,0.05)" : "transparent"} />
            {series.map((s, si) => {
              const v = s.points[i].value;
              const bx = PAD.l + slot * i + slot / 2 - (series.length * (bw + 2)) / 2 + si * (bw + 2);
              const bh = Math.max(v > 0 ? 2 : 0, (v / max) * ih);
              return <path key={s.label} d={`M${bx},${PAD.t + ih} v${-bh + 3} q0,-3 3,-3 h${bw - 6} q3,0 3,3 v${bh - 3} z`} fill={s.color} />;
            })}
          </g>
        ))}
      </svg>
      {hover !== null && (
        <div className="tip" style={{ left: `${((PAD.l + slot * hover + slot / 2) / W) * 100}%`, top: 0 }}>
          <b>{shortDay(pts[hover].date)}</b>
          {series.map((s) => (
            <div key={s.label}>
              <span>
                <i style={{ display: "inline-block", width: 8, height: 8, borderRadius: 2, background: s.color, marginInlineEnd: 6 }} />
                {s.label}
              </span>
              <b style={{ margin: 0 }}>{format(s.points[hover].value)}</b>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Ranked horizontal bars: rows = [{name, count}] — every row labelled with its value (no hover needed). */
export function HBars({ rows, color = SERIES.navy, format = num, empty = "لا توجد بيانات." }) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  if (!rows.length) return <p style={{ color: "var(--muted)", fontSize: "0.88rem" }}>{empty}</p>;
  return (
    <div className="hbar">
      {rows.map((r) => (
        <div className="r" key={r.name}>
          <span style={{ overflowWrap: "anywhere" }}>{r.name}</span>
          <span className="t">
            <i style={{ width: `${(r.count / max) * 100}%`, background: color }} />
          </span>
          <span className="n">{format(r.count)}</span>
        </div>
      ))}
    </div>
  );
}

/** Merge {created:[..],resolved:[..]} series objects into LineChart/ChartCard inputs. */
export const toSeries = (defs) => defs.map(([label, color, points]) => ({ label, color, points: points || [] }));
export const tableOf = (cols, series) => ({
  columns: ["التاريخ", ...cols],
  rows: (series[0]?.points || []).map((p, i) => [shortDay(p.date), ...series.map((s) => num(s.points[i]?.value))]),
});
export const sumSeries = (pts = []) => pts.reduce((a, p) => a + p.value, 0);

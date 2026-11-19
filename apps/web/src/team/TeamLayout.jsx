import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  Activity,
  BarChart3,
  Bell,
  BellRing,
  BookMarked,
  Bot,
  Building2,
  ChevronDown,
  ClipboardList,
  CreditCard,
  FileBarChart,
  GraduationCap,
  HeartPulse,
  Inbox,
  LayoutDashboard,
  LifeBuoy,
  ListChecks,
  LogOut,
  Menu,
  MessageSquareWarning,
  PanelRightClose,
  PanelRightOpen,
  ReceiptText,
  Search,
  Settings,
  ShieldCheck,
  Tags,
  Timer,
  UserCheck,
  UserCog,
  UserRound,
  Users,
  UsersRound,
  Wallet,
  X,
} from "lucide-react";
import logo from "../assets/madar-logo.png";
import { useSession } from "../state/session.jsx";
import { controlApi } from "../lib/controlApi.js";
import { ATTENTION } from "./labels.js";
import { ControlProvider, ErrorState, Skeleton, ago, useApi, useCan, useDebounce, num } from "./kit.jsx";
import "../dashboard/dashboard.css";
import "./control.css";

// Sidebar: every entry names the permission(s) that unlock it. The server enforces the same keys on each endpoint;
// this list only decides what is drawn.
export const NAV = [
  {
    section: "نظرة عامة",
    items: [{ to: "/team", label: "لوحة التحكم", icon: LayoutDashboard, end: true, perm: ["overview.view"] }],
  },
  {
    section: "الإدارة",
    items: [
      { to: "/team/users", label: "كل المستخدمين", icon: Users, perm: ["users.view"] },
      { to: "/team/teachers", label: "المعلّمون", icon: GraduationCap, perm: ["teachers.view"] },
      { to: "/team/students", label: "الطلاب", icon: UserRound, perm: ["students.view"] },
      { to: "/team/parents", label: "أولياء الأمور", icon: UserCheck, perm: ["parents.view"] },
      { to: "/team/members", label: "أعضاء الفريق", icon: UserCog, perm: ["team.view"] },
      { to: "/team/environments", label: "البيئات التعليمية", icon: Building2, perm: ["environments.view"] },
    ],
  },
  {
    section: "عمليات الدعم",
    items: [
      { to: "/team/support", label: "مركز الدعم", icon: LifeBuoy, end: true, perm: ["tickets.view"] },
      { to: "/team/support/tickets", label: "كل التذاكر", icon: ClipboardList, perm: ["tickets.view"] },
      { to: "/team/support/mine", label: "تذاكري", icon: ListChecks, perm: ["tickets.view"] },
      { to: "/team/support/unassigned", label: "غير مسندة", icon: Inbox, perm: ["tickets.view"] },
      { to: "/team/support/complaints", label: "الشكاوى", icon: MessageSquareWarning, perm: ["tickets.view"] },
      { to: "/team/support/categories", label: "تصنيفات التذاكر", icon: Tags, perm: ["tickets.view"] },
      { to: "/team/support/analytics", label: "تحليلات الدعم", icon: Activity, perm: ["support.analytics", "tickets.view"] },
    ],
  },
  {
    section: "العمليات التجارية",
    items: [
      { to: "/team/finance", label: "الإدارة المالية", icon: Wallet, end: true, perm: ["finance.view"] },
      { to: "/team/finance/transactions", label: "المعاملات", icon: ReceiptText, perm: ["finance.view"] },
      { to: "/team/finance/subscriptions", label: "الاشتراكات", icon: CreditCard, perm: ["finance.view"] },
      { to: "/team/ai", label: "عمليات الذكاء الاصطناعي", icon: Bot, perm: ["ai.view"] },
      { to: "/team/notifications", label: "الإشعارات", icon: Bell, perm: ["notifications.view"] },
    ],
  },
  {
    section: "التحليلات",
    items: [
      { to: "/team/reports", label: "التقارير", icon: FileBarChart, perm: ["reports.view"] },
      { to: "/team/analytics/users", label: "تحليلات المستخدمين", icon: UsersRound, perm: ["reports.view"] },
      { to: "/team/analytics/finance", label: "التحليلات المالية", icon: BarChart3, perm: ["finance.view"] },
      { to: "/team/analytics/ai", label: "تحليلات الذكاء الاصطناعي", icon: Bot, perm: ["ai.view"] },
    ],
  },
  {
    section: "النظام",
    items: [
      { to: "/team/system/health", label: "صحة النظام", icon: HeartPulse, perm: ["system.view"] },
      { to: "/team/system/jobs", label: "العمليات الخلفية", icon: Timer, perm: ["system.view"] },
      { to: "/team/audit", label: "سجل التدقيق", icon: ShieldCheck, perm: ["audit.view"] },
      { to: "/team/roles", label: "الأدوار والصلاحيات", icon: ShieldCheck, perm: ["roles.view"] },
      { to: "/team/settings", label: "الإعدادات", icon: Settings, perm: ["settings.view"] },
    ],
  },
  {
    section: "المحتوى",
    items: [{ to: "/team/knowledge", label: "قاعدة المعرفة", icon: BookMarked, perm: ["knowledge.manage"] }],
  },
];

// attention key -> nav path that should carry the red counter
const BADGE_TO = { unassigned_tickets: "/team/support/unassigned", critical_complaints: "/team/support/complaints", overdue_tickets: "/team/support/tickets" };

function Sidebar({ badges, onNavigate }) {
  const can = useCan();
  return (
    <nav className="cc-nav" aria-label="أقسام مركز التحكم">
      {NAV.map((g) => {
        const items = g.items.filter((i) => can(...i.perm));
        if (!items.length) return null;
        return (
          <div key={g.section} style={{ display: "contents" }}>
            <div className="cc-sec">{g.section}</div>
            {items.map(({ to, label, icon: Icon, end }) => (
              <NavLink key={to} to={to} end={end} onClick={onNavigate} title={label} className={({ isActive }) => "cc-link" + (isActive ? " active" : "")}>
                <Icon size={18} />
                <span className="lbl">{label}</span>
                {badges[to] > 0 && (
                  <span className="cnt" aria-label={`${badges[to]} تحتاج انتباهًا`}>
                    {badges[to] > 99 ? "99+" : num(badges[to])}
                  </span>
                )}
              </NavLink>
            ))}
          </div>
        );
      })}
    </nav>
  );
}

function useOutside(ref, onOut) {
  useEffect(() => {
    const h = (e) => ref.current && !ref.current.contains(e.target) && onOut();
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [ref, onOut]);
}

function GlobalSearch() {
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const term = useDebounce(q.trim(), 300);
  const box = useRef(null);
  useOutside(box, () => setOpen(false));
  const res = useApi(() => controlApi.search(term), [term], { skip: term.length < 2 });
  const groups = [
    ["users", "المستخدمون"],
    ["tickets", "التذاكر"],
    ["environments", "البيئات"],
  ];
  const any = res.data && groups.some(([k]) => res.data[k].length);
  return (
    <div className="cc-search" ref={box} role="search">
      <input
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
        placeholder="ابحث عن مستخدم أو تذكرة أو بيئة…"
        aria-label="بحث عام"
      />
      <Search size={17} aria-hidden="true" />
      {open && term.length >= 2 && (
        <div className="cc-pop">
          {res.loading && !res.data && <div className="empty">جارٍ البحث…</div>}
          {res.error && <div className="empty">تعذّر البحث.</div>}
          {res.data && !any && <div className="empty">لا توجد نتائج.</div>}
          {res.data &&
            groups.map(([k, label]) =>
              res.data[k].length ? (
                <div key={k}>
                  <h4>{label}</h4>
                  {res.data[k].map((r) => (
                    <button
                      key={r.link}
                      className="row"
                      onClick={() => {
                        setOpen(false);
                        setQ("");
                        nav(r.link);
                      }}
                    >
                      {r.name}
                    </button>
                  ))}
                </div>
              ) : null
            )}
        </div>
      )}
    </div>
  );
}

function NotificationCenter({ feed }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useOutside(ref, () => setOpen(false));
  const items = feed?.attention || [];
  const total = items.reduce((a, i) => a + i.count, 0);
  const nav = useNavigate();
  return (
    <div className="cc-menu" ref={ref}>
      <button className="cc-icon-btn" aria-label={`التنبيهات${total ? ` (${total})` : ""}`} aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <BellRing size={19} />
        {total > 0 && <span className="dot">{total > 99 ? "99+" : num(total)}</span>}
      </button>
      {open && (
        <div className="cc-pop" style={{ width: 340, insetInlineStart: "auto", insetInlineEnd: 0 }}>
          <h4>يحتاج انتباهًا</h4>
          {items.length === 0 && <div className="empty">لا توجد تنبيهات الآن. كل شيء على ما يرام.</div>}
          {items.map((a) => (
            <button
              key={a.key}
              className="row"
              onClick={() => {
                setOpen(false);
                nav(a.link);
              }}
            >
              <span className={"cc-badge plain " + (a.severity === "high" ? "bad" : "warn")}>{num(a.count)}</span>
              <span>{(ATTENTION[a.key] || [a.key])[0]}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function UserMenu({ me }) {
  const { logout } = useSession();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useOutside(ref, () => setOpen(false));
  return (
    <div className="cc-menu" ref={ref}>
      <button className="cc-user" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span className="cc-ava">{(me.name || "؟").trim().slice(0, 1)}</span>
        <span className="nm">{me.name}</span>
        <ChevronDown size={15} />
      </button>
      {open && (
        <div className="cc-pop" role="menu" style={{ width: 240, insetInlineStart: "auto", insetInlineEnd: 0 }}>
          <div style={{ padding: "8px 10px 10px", borderBottom: "1px solid var(--line)", marginBottom: 4 }}>
            <div style={{ fontWeight: 700 }}>{me.name}</div>
            <div style={{ fontSize: "0.8rem", color: "var(--muted)" }}>{me.role_name}</div>
          </div>
          <button
            className="row"
            role="menuitem"
            onClick={async () => {
              await logout();
              nav("/", { replace: true });
            }}
          >
            <LogOut size={16} /> تسجيل الخروج
          </button>
        </div>
      )}
    </div>
  );
}

function Shell({ me }) {
  const can = useCan();
  const loc = useLocation();
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem("madar.cc.collapsed") === "1";
    } catch {
      return false;
    }
  });
  const [drawer, setDrawer] = useState(false);
  const [feed, setFeed] = useState(null);
  const canFeed = can("overview.view");

  useEffect(() => {
    setDrawer(false);
  }, [loc.pathname]);
  useEffect(() => {
    document.body.style.overflow = drawer ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [drawer]);
  const toggleCollapse = () =>
    setCollapsed((c) => {
      try {
        localStorage.setItem("madar.cc.collapsed", c ? "0" : "1");
      } catch {
        /* UI preference only */
      }
      return !c;
    });

  // The attention list doubles as the notification centre and as the nav counters; it refreshes every minute.
  const refresh = useCallback(() => {
    if (canFeed) controlApi.feed().then(setFeed).catch(() => {});
  }, [canFeed]);
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 60000);
    return () => clearInterval(t);
  }, [refresh]);

  const badges = useMemo(() => {
    const b = {};
    (feed?.attention || []).forEach((a) => BADGE_TO[a.key] && (b[BADGE_TO[a.key]] = (b[BADGE_TO[a.key]] || 0) + a.count));
    return b;
  }, [feed]);

  return (
    <div className={"cc" + (collapsed ? " collapsed" : "") + (drawer ? " drawer" : "")}>
      <div className="cc-scrim" onClick={() => setDrawer(false)} aria-hidden="true" />
      <aside className="cc-side" aria-label="القائمة الرئيسية">
        <div className="cc-brand">
          <img src={logo} alt="مدار Madar" />
          <span className="cc-tag">CONTROL CENTER</span>
          <button className="cc-icon-btn" style={{ marginInlineStart: "auto" }} onClick={() => setDrawer(false)} aria-label="إغلاق القائمة" hidden={!drawer}>
            <X size={18} />
          </button>
        </div>
        <Sidebar badges={badges} onNavigate={() => setDrawer(false)} />
      </aside>
      <div className="cc-main">
        <header className="cc-top">
          <button className="cc-icon-btn" onClick={() => setDrawer(true)} aria-label="فتح القائمة" style={{ display: "none" }} id="cc-burger">
            <Menu size={20} />
          </button>
          <button className="cc-icon-btn" onClick={toggleCollapse} aria-label={collapsed ? "توسيع القائمة" : "طيّ القائمة"} id="cc-collapse">
            {collapsed ? <PanelRightOpen size={19} /> : <PanelRightClose size={19} />}
          </button>
          {can("overview.view") && <GlobalSearch />}
          <span style={{ flex: 1 }} />
          {canFeed && <NotificationCenter feed={feed} />}
          <UserMenu me={me} />
        </header>
        <main className="cc-body" id="cc-main">
          <div className="cc-wrap">
            <Suspense fallback={<Skeleton rows={8} />}>
              <Outlet context={{ refreshFeed: refresh }} />
            </Suspense>
          </div>
        </main>
      </div>
      <style>{`
        @media (max-width: 900px) { #cc-burger { display: grid !important; } #cc-collapse { display: none; } }
      `}</style>
    </div>
  );
}

/** Loads who the signed-in member is and what they may do, then draws the shell. */
export default function TeamLayout() {
  const me = useApi(() => controlApi.me(), []);
  if (me.error && !me.data) {
    return (
      <div className="cc-gate">
        <ErrorState error={me.error} onRetry={me.reload} />
      </div>
    );
  }
  if (!me.data) {
    return (
      <div className="cc-gate">
        <Skeleton rows={4} />
      </div>
    );
  }
  return (
    <ControlProvider me={me.data}>
      <Shell me={me.data} />
    </ControlProvider>
  );
}

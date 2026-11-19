import { useCallback, useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Menu, X, ChevronDown, LogOut, Settings as SettingsIcon, Plus, Ellipsis } from "lucide-react";
import logo from "../assets/madar-logo.png";
import { useSession } from "../state/session.jsx";
import { useEnvironment } from "../state/environment.jsx";
import { notificationsApi } from "../lib/dashboardApi.js";
import { formatPhone } from "../lib/phone.js";
import { dashboardNav, dashboardNavGroups, mobileTabs, quickActions } from "./nav.js";
import BillingBanner from "./BillingBanner.jsx";
import PlansWelcome from "./PlansWelcome.jsx";
import "./billing.css";
import "./dashboard.css";
import "./shell.css";

function initialsOf(name) {
  return (name || "؟").trim().slice(0, 1);
}

function NavLinks({ onNavigate, badges = {} }) {
  return (
    <nav className="dash-nav" aria-label="أقسام لوحة التحكم">
      {dashboardNavGroups.map((g, gi) => (
        <div className="dash-group" key={g.title || gi} role="group" aria-label={g.title || undefined}>
          {g.title && <div className="dash-group-title">{g.title}</div>}
          {g.items.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              onClick={onNavigate}
              className={({ isActive }) => "dash-link" + (isActive ? " active" : "")}
            >
              <Icon size={18} />
              <span>{label}</span>
              {badges[to] > 0 && (
                <span className="dash-badge" aria-label={`${badges[to]} إشعار فشل إرساله`}>
                  {badges[to] > 99 ? "99+" : badges[to]}
                </span>
              )}
            </NavLink>
          ))}
        </div>
      ))}
    </nav>
  );
}

/** "+ جديد": the things a teacher starts most often, one tap from anywhere. */
function QuickCreate() {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const nav = useNavigate();
  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false);
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return (
    <div className="dash-quick" ref={ref}>
      <button type="button" className="dash-quick-btn" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <Plus size={16} aria-hidden="true" />
        <span>جديد</span>
      </button>
      {open && (
        <div className="dash-quick-menu" role="menu">
          {quickActions.map(({ to, label, hint, icon: Icon }) => (
            <button
              key={to}
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                nav(to);
              }}
            >
              <span className="ic" aria-hidden="true">
                <Icon size={17} />
              </span>
              <span>
                <b>{label}</b>
                <small>{hint}</small>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** Phone: the four lesson-time pages are always one thumb-tap away; everything else is under "المزيد". */
function BottomBar({ onMore, badges }) {
  return (
    <nav className="dash-bottombar" aria-label="التنقل السريع">
      {mobileTabs.map(({ to, label, icon: Icon, end }) => (
        <NavLink key={to} to={to} end={end} className={({ isActive }) => "dash-bt" + (isActive ? " active" : "")}>
          <Icon size={21} />
          <span>{label.split(" ")[0]}</span>
          {badges[to] > 0 && <i className="dash-bt-dot" aria-hidden="true" />}
        </NavLink>
      ))}
      <button type="button" className="dash-bt" onClick={onMore} aria-label="المزيد من الأقسام" aria-controls="dash-drawer">
        <Ellipsis size={21} />
        <span>المزيد</span>
      </button>
    </nav>
  );
}

function UserMenu() {
  const { user, logout } = useSession();
  const env = useEnvironment();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    const onClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const onLogout = async () => {
    setOpen(false);
    env.clear();
    await logout();
    nav("/", { replace: true });
  };

  return (
    <div className="dash-user" ref={ref}>
      <button
        className="dash-user-btn"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <span className="dash-ava">{initialsOf(user?.name)}</span>
        <ChevronDown size={15} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            className="dash-user-menu"
            role="menu"
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.16 }}
          >
            <div className="who">
              <div className="n">{user?.name}</div>
              <div className="e">
                <bdi dir="ltr">{user?.email || (user?.phone ? formatPhone(user.phone) : "")}</bdi>
              </div>
            </div>
            <button
              onClick={() => {
                setOpen(false);
                nav("/app/settings");
              }}
            >
              <SettingsIcon size={16} /> الإعدادات
            </button>
            <button className="danger" onClick={onLogout}>
              <LogOut size={16} /> تسجيل الخروج
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default function DashboardLayout() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const env = useEnvironment();
  const location = useLocation();
  const [failed, setFailed] = useState(0);
  const refreshFailed = useCallback(() => {
    notificationsApi
      .summary()
      .then((d) => setFailed(d.failed))
      .catch(() => {});
  }, []);
  useEffect(() => {
    refreshFailed();
    const t = setInterval(refreshFailed, 60000);
    return () => clearInterval(t);
  }, [refreshFailed]);
  const badges = { "/app/notifications": failed };
  const current = dashboardNav.find((n) =>
    n.end ? location.pathname === n.to : location.pathname.startsWith(n.to)
  );

  useEffect(() => {
    setDrawerOpen(false);
  }, [location.pathname]);
  useEffect(() => {
    document.body.style.overflow = drawerOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [drawerOpen]);

  // The drawer is a modal dialog on small screens: Escape closes it, focus moves into it when it
  // opens and returns to the button that opened it when it closes.
  const menuBtnRef = useRef(null);
  const closeBtnRef = useRef(null);
  useEffect(() => {
    if (!drawerOpen) return undefined;
    const opener = menuBtnRef.current;
    closeBtnRef.current?.focus();
    const onKey = (e) => {
      if (e.key === "Escape") setDrawerOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      opener?.focus?.();
    };
  }, [drawerOpen]);

  return (
    <div className="dash">
      <aside className="dash-side">
        <div className="dash-brand">
          <img src={logo} alt="مدار Madar" />
        </div>
        <NavLinks badges={badges} />
      </aside>

      <AnimatePresence>
        {drawerOpen && (
          <>
            <motion.div
              className="dash-drawer-back"
              onClick={() => setDrawerOpen(false)}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            />
            <motion.div
              id="dash-drawer"
              className="dash-drawer"
              role="dialog"
              aria-modal="true"
              aria-label="القائمة"
              initial={{ x: "100%" }}
              animate={{ x: 0 }}
              exit={{ x: "100%" }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            >
              <div className="dash-drawer-top">
                <img src={logo} alt="مدار Madar" />
                <button
                  ref={closeBtnRef}
                  type="button"
                  className="dash-drawer-close"
                  aria-label="إغلاق القائمة"
                  onClick={() => setDrawerOpen(false)}
                >
                  <X size={18} />
                </button>
              </div>
              <NavLinks badges={badges} onNavigate={() => setDrawerOpen(false)} />
            </motion.div>
          </>
        )}
      </AnimatePresence>

      <div className="dash-main">
        <header className="dash-top">
          <div className="dash-top-start">
            <button
              ref={menuBtnRef}
              type="button"
              className="dash-menu-btn"
              aria-label="القائمة"
              aria-expanded={drawerOpen}
              aria-controls="dash-drawer"
              onClick={() => setDrawerOpen(true)}
            >
              <Menu size={19} />
            </button>
            <div className="dash-title">{current?.label || "مدار"}</div>
          </div>
          <div className="dash-top-end">
            <QuickCreate />
            {env.environment && (
              <div className="dash-env">
                <span className="ic" aria-hidden="true" />
                <span className="name">{env.environment.name}</span>
                <NavLink to="/auth/teacher/environments" className="dash-env-switch">
                  تبديل
                </NavLink>
              </div>
            )}
            <UserMenu />
          </div>
        </header>
        <main className="dash-body">
          <BillingBanner />
          <PlansWelcome />
          <Outlet context={{ refreshFailed }} />
        </main>
        <BottomBar onMore={() => setDrawerOpen(true)} badges={badges} />
      </div>
    </div>
  );
}

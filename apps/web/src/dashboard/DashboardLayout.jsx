import { useCallback, useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Menu, X, ChevronDown, LogOut, Settings as SettingsIcon } from "lucide-react";
import logo from "../assets/madar-logo.png";
import { useSession } from "../state/session.jsx";
import { useEnvironment } from "../state/environment.jsx";
import { notificationsApi } from "../lib/dashboardApi.js";
import { dashboardNav } from "./nav.js";
import "./dashboard.css";

function initialsOf(name) {
  return (name || "؟").trim().slice(0, 1);
}

function NavLinks({ onNavigate, badges = {} }) {
  return (
    <nav className="dash-nav" aria-label="أقسام لوحة التحكم">
      {dashboardNav.map(({ to, label, icon: Icon, end }) => (
        <NavLink key={to} to={to} end={end} onClick={onNavigate} className={({ isActive }) => "dash-link" + (isActive ? " active" : "")}>
          <Icon size={18} />
          <span>{label}</span>
          {badges[to] > 0 && <span className="dash-badge" aria-label={`${badges[to]} إشعار فشل إرساله`}>{badges[to] > 99 ? "99+" : badges[to]}</span>}
        </NavLink>
      ))}
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
    const onClick = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const onLogout = async () => {
    setOpen(false);
    env.clear();
    await logout();
    nav("/auth/teacher/login", { replace: true });
  };

  return (
    <div className="dash-user" ref={ref}>
      <button className="dash-user-btn" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-haspopup="menu">
        <span className="dash-ava">{initialsOf(user?.name)}</span>
        <ChevronDown size={15} />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            className="dash-user-menu" role="menu"
            initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.16 }}
          >
            <div className="who">
              <div className="n">{user?.name}</div>
              <div className="e">{user?.email || user?.phone}</div>
            </div>
            <button onClick={() => { setOpen(false); nav("/app/settings"); }}>
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
    notificationsApi.summary().then((d) => setFailed(d.failed)).catch(() => {});
  }, []);
  useEffect(() => {
    refreshFailed();
    const t = setInterval(refreshFailed, 60000);
    return () => clearInterval(t);
  }, [refreshFailed]);
  const badges = { "/app/notifications": failed };
  const current = dashboardNav.find((n) => (n.end ? location.pathname === n.to : location.pathname.startsWith(n.to)));

  useEffect(() => { setDrawerOpen(false); }, [location.pathname]);
  useEffect(() => { document.body.style.overflow = drawerOpen ? "hidden" : ""; return () => { document.body.style.overflow = ""; }; }, [drawerOpen]);

  return (
    <div className="dash">
      <aside className="dash-side">
        <div className="dash-brand"><img src={logo} alt="مدار Madar" /></div>
        <NavLinks badges={badges} />
      </aside>

      <AnimatePresence>
        {drawerOpen && (
          <>
            <motion.div className="dash-drawer-back" onClick={() => setDrawerOpen(false)} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
            <motion.div
              className="dash-drawer"
              initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            >
              <div className="dash-drawer-top">
                <img src={logo} alt="مدار Madar" />
                <button className="dash-drawer-close" aria-label="إغلاق القائمة" onClick={() => setDrawerOpen(false)}><X size={18} /></button>
              </div>
              <NavLinks badges={badges} onNavigate={() => setDrawerOpen(false)} />
            </motion.div>
          </>
        )}
      </AnimatePresence>

      <div className="dash-main">
        <header className="dash-top">
          <div className="dash-top-start">
            <button className="dash-menu-btn" aria-label="القائمة" onClick={() => setDrawerOpen(true)}><Menu size={19} /></button>
            <div className="dash-title">{current?.label || "مدار"}</div>
          </div>
          <div className="dash-top-end">
            {env.environment && (
              <div className="dash-env">
                <span className="ic" aria-hidden="true" />
                <span className="name">{env.environment.name}</span>
                <NavLink to="/auth/teacher/environments" className="dash-env-switch">تبديل</NavLink>
              </div>
            )}
            <UserMenu />
          </div>
        </header>
        <main className="dash-body">
          <Outlet context={{ refreshFailed }} />
        </main>
      </div>
    </div>
  );
}

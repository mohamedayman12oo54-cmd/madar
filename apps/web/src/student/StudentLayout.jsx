import { useCallback, useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  Bell,
  Home,
  ClipboardList,
  PlayCircle,
  FileQuestion,
  Sparkles,
  LogOut,
  Settings,
} from "lucide-react";
import logo from "../assets/madar-logo.png";
import { useSession } from "../state/session.jsx";
import { useEnvironment } from "../state/environment.jsx";
import { studentApi } from "../lib/studentApi.js";
import "../dashboard/dashboard.css";
import "./student.css";

export const studentNav = [
  { to: "/learn", label: "الرئيسية", icon: Home, end: true },
  { to: "/learn/records", label: "سجلّي", icon: ClipboardList },
  { to: "/learn/videos", label: "الفيديوهات", icon: PlayCircle },
  { to: "/learn/quizzes", label: "اختباراتي", icon: FileQuestion },
  { to: "/learn/assistant", label: "المساعد", icon: Sparkles },
];

export default function StudentLayout() {
  const { logout } = useSession();
  const env = useEnvironment();
  const nav = useNavigate();
  const [unread, setUnread] = useState(0);

  const refreshUnread = useCallback(() => {
    studentApi.notifications
      .list({ unread: 1 })
      .then((d) => setUnread((d.results || []).length))
      .catch(() => {});
  }, []);
  useEffect(() => {
    refreshUnread();
    const t = setInterval(refreshUnread, 60000);
    return () => clearInterval(t);
  }, [refreshUnread]);

  const onLogout = async () => {
    env.clear();
    await logout();
    nav("/auth/student", { replace: true });
  };

  return (
    <div className="stu">
      <header className="stu-top">
        <div className="brand">
          <img src={logo} alt="مدار Madar" />
        </div>
        <div className="stu-env">
          {env.environment && (
            <>
              <span className="name">{env.environment.name}</span>
              <NavLink to="/auth/student/environments" className="dash-env-switch">
                تبديل
              </NavLink>
            </>
          )}
        </div>
        <div className="stu-top-end">
          <NavLink
            to="/learn/notifications"
            className="stu-icon-btn"
            aria-label={unread ? `الإشعارات — ${unread} غير مقروء` : "الإشعارات"}
          >
            <Bell size={18} />
            {unread > 0 && <span className="dash-badge">{unread > 99 ? "99+" : unread}</span>}
          </NavLink>
          <NavLink to="/learn/settings" className="stu-icon-btn" aria-label="الإعدادات">
            <Settings size={18} />
          </NavLink>
          <button className="stu-icon-btn" aria-label="تسجيل الخروج" onClick={onLogout}>
            <LogOut size={18} />
          </button>
        </div>
      </header>
      <main className="stu-body">
        <Outlet context={{ refreshUnread }} />
      </main>
      <nav className="stu-tabs" aria-label="أقسام مدار للطالب">
        {studentNav.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) => "stu-tab" + (isActive ? " active" : "")}
          >
            <Icon size={20} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}

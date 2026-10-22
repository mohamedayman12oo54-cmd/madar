import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { BookMarked, LogOut } from "lucide-react";
import logo from "../assets/madar-logo.png";
import { useSession } from "../state/session.jsx";
import "../dashboard/dashboard.css";

/** Shell for the team area. Same visual language as the teacher dashboard, one section. */
export default function TeamLayout() {
  const { user, logout } = useSession();
  const nav = useNavigate();

  const onLogout = async () => {
    await logout();
    nav("/auth/team/login", { replace: true });
  };

  return (
    <div className="dash">
      <aside className="dash-side">
        <div className="dash-brand">
          <img src={logo} alt="مدار Madar" />
        </div>
        <nav className="dash-nav" aria-label="أقسام فريق مدار">
          <NavLink to="/team" end className={({ isActive }) => "dash-link" + (isActive ? " active" : "")}>
            <BookMarked size={18} />
            <span>قاعدة المعرفة</span>
          </NavLink>
        </nav>
      </aside>

      <div className="dash-main">
        <header className="dash-top">
          <div className="dash-top-start">
            <div className="dash-title">قاعدة المعرفة</div>
          </div>
          <div className="dash-top-end">
            <span className="stat-sub" aria-label="الحساب">
              {user?.name}
            </span>
            <button type="button" className="mini-btn" onClick={onLogout}>
              <LogOut size={15} aria-hidden="true" /> تسجيل الخروج
            </button>
          </div>
        </header>
        <main className="dash-body">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

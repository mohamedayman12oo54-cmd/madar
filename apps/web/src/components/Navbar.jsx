import { useState, useEffect } from "react";
import { NavLink, Link } from "react-router-dom";
import { Menu, X, ArrowLeft } from "lucide-react";
import logo from "../assets/madar-logo.png";
import { navItems } from "../data/content";
import { useSession } from "../state/session.jsx";

// Where each kind of signed-in account lands (the guardian portal has no account, so no entry here).
const AREA = { teacher: "/app", student: "/learn", team: "/team" };

// NOTE: the shell is a plain <div> (no transform) so the glass backdrop-filter
// renders correctly in Safari — a transformed ancestor breaks it into a dark box.
export default function Navbar() {
  const [tight, setTight] = useState(false);
  const [open, setOpen] = useState(false);
  const { status, user } = useSession();
  const area = status === "authenticated" ? AREA[user?.role] : null;

  useEffect(() => {
    const on = () => setTight(window.scrollY > 12);
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);
  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
  }, [open]);

  return (
    <>
      <div className="nav-shell">
        <nav className={"nav" + (tight ? " tight" : "")} aria-label="التنقل الرئيسي">
          <Link to="/" className="brand">
            <img src={logo} alt="مدار Madar" />
          </Link>
          <div className="nlinks">
            {navItems.map((i) => (
              <NavLink
                key={i.to}
                to={i.to}
                end={i.to === "/"}
                className={({ isActive }) => (isActive ? "active" : "")}
              >
                {i.label}
              </NavLink>
            ))}
          </div>
          <div className="nactions">
            {area ? (
              <Link className="btn btn-primary" to={area}>
                لوحتي <ArrowLeft className="arw" size={16} />
              </Link>
            ) : (
              <>
                <Link className="btn btn-ghost" to="/auth">
                  تسجيل الدخول
                </Link>
                <Link className="btn btn-primary" to="/auth">
                  ابدأ الآن <ArrowLeft className="arw" size={16} />
                </Link>
              </>
            )}
            <button className="burger" aria-label="القائمة" onClick={() => setOpen(true)}>
              <Menu size={20} />
            </button>
          </div>
        </nav>
      </div>

      <div className={"mm" + (open ? " open" : "")}>
        <div className="mm-top">
          <img src={logo} alt="مدار" />
          <button className="burger" aria-label="إغلاق" onClick={() => setOpen(false)}>
            <X size={20} />
          </button>
        </div>
        {navItems.map((i) => (
          <NavLink key={i.to} to={i.to} end={i.to === "/"} onClick={() => setOpen(false)}>
            {i.label}
          </NavLink>
        ))}
        <Link className="btn btn-primary" to={area || "/auth"} onClick={() => setOpen(false)}>
          {area ? "لوحتي" : "ابدأ الآن"}
        </Link>
      </div>
    </>
  );
}

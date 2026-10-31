// Phase 1 — route guard. Wrap protected route trees with:
//   <Route element={<ProtectedRoute role="teacher" requireEnvironment />}>
//     <Route path="/app" element={<DashboardLayout />}>...</Route>
//   </Route>
// Renders <Outlet/> only once the session is confirmed authenticated (and,
// if requireEnvironment, an environment has been confirmed active by the
// backend) — otherwise redirects to the right auth step. All the actual
// authorization happens server-side (see accounts/authentication.py and
// environments/tenancy.py); this only decides what the SPA shows.
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { OrbitBig } from "../auth/ui.jsx";
import { useEnvironment } from "../state/environment.jsx";
import { useSession } from "../state/session.jsx";

const LOGIN_PATH = {
  teacher: "/auth/teacher/login",
  student: "/auth/student",
  team: "/auth/team/login",
};
const ENV_SELECT_PATH = {
  teacher: "/auth/teacher/environments",
  student: "/auth/student/environments",
};

function Boot({ offline = false }) {
  return (
    <div className="dash-boot" role="status" aria-label="جارٍ التحقق من الجلسة">
      <OrbitBig />
      {offline && <p className="boot-note">تعذّر الاتصال بالخادم. جلستك محفوظة، ونعيد المحاولة تلقائيًا…</p>}
    </div>
  );
}

export default function ProtectedRoute({ role, requireEnvironment = false }) {
  const { status, user, offline } = useSession();
  const env = useEnvironment();
  const location = useLocation();

  if (status === "loading") return <Boot offline={offline} />;

  if (status !== "authenticated") {
    return <Navigate to={LOGIN_PATH[role] || "/auth"} replace state={{ from: location }} />;
  }

  if (role && user?.role !== role) {
    // Authenticated, but as the wrong kind of account for this area.
    return <Navigate to="/auth" replace />;
  }

  if (requireEnvironment) {
    if (env.status === "idle" || env.status === "checking") return <Boot />;
    if (env.status !== "ready") {
      return <Navigate to={ENV_SELECT_PATH[role] || "/auth"} replace />;
    }
  }

  return <Outlet />;
}

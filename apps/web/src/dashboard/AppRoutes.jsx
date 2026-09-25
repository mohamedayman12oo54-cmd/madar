import { Route, Routes } from "react-router-dom";
import ProtectedRoute from "../components/ProtectedRoute.jsx";
import DashboardLayout from "./DashboardLayout.jsx";
import OverviewPage from "./OverviewPage.jsx";
import ComingSoon from "./ComingSoon.jsx";

const SECTIONS = [
  ["students", "الطلاب"],
  ["groups", "المجموعات"],
  ["sessions", "الجلسات"],
  ["attendance", "الحضور"],
  ["evaluation", "التقييم"],
  ["financials", "المدفوعات"],
  ["content", "المحتوى التعليمي"],
  ["ai", "المساعد الذكي"],
  ["notifications", "الإشعارات"],
  ["settings", "الإعدادات"],
];

export default function AppRoutes() {
  return (
    <Routes>
      <Route element={<ProtectedRoute role="teacher" requireEnvironment />}>
        <Route path="/app" element={<DashboardLayout />}>
          <Route index element={<OverviewPage />} />
          {SECTIONS.map(([path, label]) => (
            <Route key={path} path={path} element={<ComingSoon title={label} />} />
          ))}
        </Route>
      </Route>
    </Routes>
  );
}

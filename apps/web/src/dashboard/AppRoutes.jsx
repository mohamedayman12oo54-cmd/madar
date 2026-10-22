import { Route, Routes } from "react-router-dom";
import ProtectedRoute from "../components/ProtectedRoute.jsx";
import DashboardLayout from "./DashboardLayout.jsx";
import OverviewPage from "./OverviewPage.jsx";
import StudentsPage from "./StudentsPage.jsx";
import GroupsPage from "./GroupsPage.jsx";
import SessionsPage from "./SessionsPage.jsx";
import AttendancePage from "./AttendancePage.jsx";
import EvaluationPage from "./EvaluationPage.jsx";
import ScannerPage from "./ScannerPage.jsx";
import FinancialsPage from "./FinancialsPage.jsx";
import ContentPage from "./ContentPage.jsx";
import NotificationsPage from "./NotificationsPage.jsx";
import SettingsPage from "./SettingsPage.jsx";
import BillingPage from "./BillingPage.jsx";

export default function AppRoutes() {
  return (
    <Routes>
      <Route element={<ProtectedRoute role="teacher" requireEnvironment />}>
        <Route path="/app" element={<DashboardLayout />}>
          <Route index element={<OverviewPage />} />
          <Route path="students" element={<StudentsPage />} />
          <Route path="groups" element={<GroupsPage />} />
          <Route path="sessions" element={<SessionsPage />} />
          <Route path="attendance" element={<AttendancePage />} />
          <Route path="scan" element={<ScannerPage />} />
          <Route path="evaluation" element={<EvaluationPage />} />
          <Route path="financials" element={<FinancialsPage />} />
          <Route path="content" element={<ContentPage />} />
          <Route path="notifications" element={<NotificationsPage />} />
          <Route path="billing" element={<BillingPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Route>
    </Routes>
  );
}

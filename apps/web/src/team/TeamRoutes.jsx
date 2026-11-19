import { lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import ProtectedRoute from "../components/ProtectedRoute.jsx";
import TeamLayout from "./TeamLayout.jsx";
import { EmptyState, useCan } from "./kit.jsx";

const KnowledgePage = lazy(() => import("./KnowledgePage.jsx"));
const Overview = lazy(() => import("./pages/OverviewPage.jsx"));
const U = (name) => lazy(() => import("./pages/UsersPages.jsx").then((m) => ({ default: m[name] })));
const T = (name) => lazy(() => import("./pages/TeamPages.jsx").then((m) => ({ default: m[name] })));
const S = (name) => lazy(() => import("./pages/SupportPages.jsx").then((m) => ({ default: m[name] })));
const B = (name) => lazy(() => import("./pages/BusinessPages.jsx").then((m) => ({ default: m[name] })));
const Y = (name) => lazy(() => import("./pages/SystemPages.jsx").then((m) => ({ default: m[name] })));

const UsersPage = U("UsersPage");
const UserDetailPage = U("UserDetailPage");
const ParentsPage = U("ParentsPage");
const ParentDetailPage = U("ParentDetailPage");
const MembersPage = T("MembersPage");
const MemberDetailPage = T("MemberDetailPage");
const RolesPage = T("RolesPage");
const EnvironmentsPage = T("EnvironmentsPage");
const EnvironmentDetailPage = T("EnvironmentDetailPage");
const SupportCenterPage = S("SupportCenterPage");
const TicketsPage = S("TicketsPage");
const TicketDetailPage = S("TicketDetailPage");
const CategoriesPage = S("CategoriesPage");
const SupportAnalyticsPage = S("SupportAnalyticsPage");
const FinanceOverviewPage = B("FinanceOverviewPage");
const TransactionsPage = B("TransactionsPage");
const SubscriptionsPage = B("SubscriptionsPage");
const PaymentIssuesPage = B("PaymentIssuesPage");
const AiPage = B("AiPage");
const AiDetailPage = B("AiDetailPage");
const NotificationsPage = B("NotificationsPage");
const ReportsPage = Y("ReportsPage");
const AnalyticsPage = Y("AnalyticsPage");
const AuditPage = Y("AuditPage");
const HealthPage = Y("HealthPage");
const JobsPage = Y("JobsPage");
const SettingsPage = Y("SettingsPage");

/** The Knowledge Base page is not part of the Control Center API, so it gets its own client-side gate (the server
 *  enforces the same permission on every /knowledge request). */
function NeedsKnowledge({ children }) {
  const can = useCan();
  return can("knowledge.manage") ? children : <EmptyState title="لا تملك الصلاحية" text="قاعدة المعرفة تتطلب صلاحية «إدارة قاعدة المعرفة»." />;
}

/** The landing page depends on what the member may open: the overview, or (legacy accounts) the Knowledge Base. */
function Home() {
  const can = useCan();
  return can("overview.view") ? <Overview /> : <Navigate to="/team/knowledge" replace />;
}

/** The Madar Control Center (role "team"). Not tenant-scoped: only a signed-in team account is needed, and every
 *  endpoint checks the member's permission on the server. */
export default function TeamRoutes() {
  return (
    <Routes>
      <Route element={<ProtectedRoute role="team" />}>
        <Route path="/team" element={<TeamLayout />}>
          <Route index element={<Home />} />
          <Route path="users" element={<UsersPage kind="all" />} />
          <Route path="users/:id" element={<UserDetailPage />} />
          <Route path="teachers" element={<UsersPage kind="teachers" />} />
          <Route path="students" element={<UsersPage kind="students" />} />
          <Route path="parents" element={<ParentsPage />} />
          <Route path="parents/:phone" element={<ParentDetailPage />} />
          <Route path="members" element={<MembersPage />} />
          <Route path="members/:id" element={<MemberDetailPage />} />
          <Route path="roles" element={<RolesPage />} />
          <Route path="environments" element={<EnvironmentsPage />} />
          <Route path="environments/:id" element={<EnvironmentDetailPage />} />
          <Route path="support" element={<SupportCenterPage />} />
          <Route path="support/tickets" element={<TicketsPage mode="all" />} />
          <Route path="support/mine" element={<TicketsPage mode="mine" />} />
          <Route path="support/unassigned" element={<TicketsPage mode="unassigned" />} />
          <Route path="support/complaints" element={<TicketsPage mode="complaints" />} />
          <Route path="support/tickets/:id" element={<TicketDetailPage />} />
          <Route path="support/categories" element={<CategoriesPage />} />
          <Route path="support/analytics" element={<SupportAnalyticsPage />} />
          <Route path="finance" element={<FinanceOverviewPage />} />
          <Route path="finance/transactions" element={<TransactionsPage />} />
          <Route path="finance/subscriptions" element={<SubscriptionsPage />} />
          <Route path="finance/issues" element={<PaymentIssuesPage />} />
          <Route path="ai" element={<AiPage />} />
          <Route path="ai/:id" element={<AiDetailPage />} />
          <Route path="notifications" element={<NotificationsPage />} />
          <Route path="reports" element={<ReportsPage />} />
          <Route path="reports/:name" element={<ReportsPage />} />
          <Route path="analytics/:kind" element={<AnalyticsPage />} />
          <Route path="audit" element={<AuditPage />} />
          <Route path="system/health" element={<HealthPage />} />
          <Route path="system/jobs" element={<JobsPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="knowledge" element={<NeedsKnowledge><KnowledgePage /></NeedsKnowledge>} />
          <Route path="*" element={<Navigate to="/team" replace />} />
        </Route>
      </Route>
    </Routes>
  );
}

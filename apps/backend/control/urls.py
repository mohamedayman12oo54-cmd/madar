from django.urls import path

from . import business, environments, overview, reports, support, system, team, users

urlpatterns = [
    # --- session / shell
    path("me/", team.MeView.as_view()),
    path("overview/", overview.OverviewView.as_view()),
    path("feed/", overview.ActivityFeedView.as_view()),
    path("search/", overview.SearchView.as_view()),
    path("recipients/", business.RecipientSearchView.as_view()),

    # --- users
    path("users/", users.UserListView.as_view()),
    path("users/<int:pk>/", users.UserDetailView.as_view()),
    path("users/<int:pk>/suspend/", users.UserSuspendView.as_view()),
    path("users/<int:pk>/restore/", users.UserRestoreView.as_view()),
    path("users/<int:pk>/activity/", users.UserActivityView.as_view()),
    path("users/<int:pk>/tickets/", users.UserTicketsView.as_view()),
    path("users/<int:pk>/notifications/", users.UserNotificationsView.as_view()),
    path("users/<int:pk>/history/", users.UserHistoryView.as_view()),
    path("teachers/", users.TeacherListView.as_view()),
    path("students/", users.StudentListView.as_view()),
    path("parents/", users.ParentListView.as_view()),
    path("parents/<str:phone>/", users.ParentDetailView.as_view()),

    # --- team, roles
    path("team/", team.MemberListView.as_view()),
    path("team/<int:pk>/", team.MemberDetailView.as_view()),
    path("team/<int:pk>/tickets/", team.MemberTicketsView.as_view()),
    path("team/<int:pk>/activity/", team.MemberActivityView.as_view()),
    path("roles/", team.RoleListCreateView.as_view()),
    path("roles/<int:pk>/", team.RoleDetailView.as_view()),
    path("permissions/", team.PermissionCatalogView.as_view()),

    # --- environments
    path("environments/", environments.EnvironmentListView.as_view()),
    path("environments/<int:pk>/", environments.EnvironmentDetailView.as_view()),

    # --- support (team)
    path("support/overview/", support.SupportOverviewView.as_view()),
    path("support/analytics/", support.SupportAnalyticsView.as_view()),
    path("support/agents/", support.AgentListView.as_view()),
    path("support/categories/", support.CategoryListCreateView.as_view()),
    path("support/categories/<int:pk>/", support.CategoryDetailView.as_view()),
    path("support/tickets/", support.TicketListCreateView.as_view()),
    path("support/tickets/bulk/", support.TicketBulkView.as_view()),
    path("support/tickets/<int:pk>/", support.TicketDetailView.as_view()),
    path("support/tickets/<int:pk>/messages/", support.TicketMessageView.as_view()),
    path("support/tickets/<int:pk>/status/", support.TicketStatusView.as_view()),
    path("support/tickets/<int:pk>/priority/", support.TicketPriorityView.as_view()),
    path("support/tickets/<int:pk>/category/", support.TicketCategoryChangeView.as_view()),
    path("support/tickets/<int:pk>/assign/", support.TicketAssignView.as_view()),
    path("support/attachments/<int:pk>/", support.TeamAttachmentView.as_view()),

    # --- support (customers: teachers and students, their OWN tickets only)
    path("customer/categories/", support.CustomerCategoriesView.as_view()),
    path("customer/tickets/", support.CustomerTicketsView.as_view()),
    path("customer/tickets/<int:pk>/", support.CustomerTicketDetailView.as_view()),
    path("customer/tickets/<int:pk>/messages/", support.CustomerMessageView.as_view()),
    path("customer/tickets/<int:pk>/rate/", support.CustomerRateView.as_view()),
    path("customer/attachments/<int:pk>/", support.CustomerAttachmentView.as_view()),

    # --- finance
    path("finance/overview/", business.FinanceOverviewView.as_view()),
    path("finance/transactions/", business.TransactionListView.as_view()),
    path("finance/subscriptions/", business.SubscriptionListView.as_view()),
    path("finance/plans/", business.PlanListView.as_view()),
    path("finance/issues/", business.PaymentIssuesView.as_view()),

    # --- AI
    path("ai/overview/", business.AIOverviewView.as_view()),
    path("ai/operations/", business.AIListView.as_view()),
    path("ai/operations/<int:pk>/", business.AIDetailView.as_view()),

    # --- notifications
    path("notifications/overview/", business.NotificationOverviewView.as_view()),
    path("notifications/", business.NotificationListView.as_view()),
    path("notifications/<int:pk>/", business.NotificationDetailView.as_view()),
    path("notifications/platform/", business.PlatformNoticeView.as_view()),
    path("notifications/templates/", business.TemplateListCreateView.as_view()),
    path("notifications/templates/<int:pk>/", business.TemplateDetailView.as_view()),

    # --- reports, audit, system, settings
    path("reports/", reports.ReportListView.as_view()),
    path("reports/<str:name>/", reports.ReportView.as_view()),
    path("audit/", system.AuditListView.as_view()),
    path("system/health/", system.HealthView.as_view()),
    path("system/jobs/", system.JobRunListView.as_view()),
    path("settings/", system.SettingsView.as_view()),
]

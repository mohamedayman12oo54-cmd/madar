from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    # logins
    path("team/login/", views.TeamLoginView.as_view()),
    path("teacher/login/", views.TeacherLoginView.as_view()),
    path("student/login/", views.StudentLoginView.as_view()),

    # teacher signup (3-step wizard: start -> otp -> environment)
    path("teacher/signup/", views.TeacherSignupStartView.as_view()),
    path("teacher/signup/environment/", views.TeacherSignupEnvironmentView.as_view()),

    # teacher forgot password (request -> otp -> reset)
    path("teacher/forgot/", views.TeacherForgotRequestView.as_view()),
    path("teacher/forgot/reset/", views.TeacherForgotResetView.as_view()),

    # student claim (request -> otp -> activate)
    path("student/claim/", views.StudentClaimRequestView.as_view()),
    path("student/claim/activate/", views.StudentClaimActivateView.as_view()),

    # student forgot password (request -> otp -> reset)
    path("student/forgot/", views.StudentForgotRequestView.as_view()),
    path("student/forgot/reset/", views.StudentForgotResetView.as_view()),

    # shared OTP endpoints — <flow> is one of teacher-signup | teacher-reset | student-claim | student-reset
    path("otp/<str:flow>/verify/", views.OTPVerifyView.as_view()),
    path("otp/<str:flow>/resend/", views.OTPResendView.as_view()),

    # session
    path("token/refresh/", TokenRefreshView.as_view()),
    path("logout/", views.LogoutView.as_view()),
    path("me/", views.MeView.as_view()),
]

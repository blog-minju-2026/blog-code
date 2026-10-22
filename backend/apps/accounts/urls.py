from django.urls import path

from . import views

urlpatterns = [
    path("auth/csrf", views.CsrfView.as_view()),
    path("auth/me", views.MeView.as_view()),
    path("auth/signup", views.SignupView.as_view()),
    path("auth/email/verify", views.EmailVerifyView.as_view()),
    path("auth/email/resend", views.EmailResendView.as_view()),
    path("auth/password/reset", views.PasswordResetView.as_view()),
    path("auth/password/reset/confirm", views.PasswordResetConfirmView.as_view()),
    path("auth/login", views.LoginView.as_view()),
    path("auth/logout", views.LogoutView.as_view()),
    path("auth/social", views.SocialStatusView.as_view()),
    path("auth/social/signup", views.SocialSignupView.as_view()),
    path("auth/nickname-available", views.NicknameAvailableView.as_view()),
    path("me", views.MeUpdateView.as_view()),
    path("me/leave", views.LeaveView.as_view()),
]

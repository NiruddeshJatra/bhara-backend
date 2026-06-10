from django.urls import path
from users.views import (
  OTPRequestView,
  OTPVerifyView,
  SignupCompleteView,
  LoginView,
  LogoutView,
  TokenRefreshView,
  PasswordResetCompleteView,
)

urlpatterns = [
  path('otp/request/', OTPRequestView.as_view(), name='otp-request'),
  path('otp/verify/', OTPVerifyView.as_view(), name='otp-verify'),
  path('signup/complete/', SignupCompleteView.as_view(), name='signup-complete'),
  path('login/', LoginView.as_view(), name='login'),
  path('logout/', LogoutView.as_view(), name='logout'),
  path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
  path('password-reset/complete/', PasswordResetCompleteView.as_view(), name='password-reset-complete'),
]

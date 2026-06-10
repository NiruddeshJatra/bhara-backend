from django.urls import path
from users.views import (
  UserProfileView,
  ProfileStep1View,
  ProfileStep2View,
)

urlpatterns = [
  path('profile/', UserProfileView.as_view(), name='user-profile'),
  path('profile/step1/', ProfileStep1View.as_view(), name='profile-step1'),
  path('profile/step2/', ProfileStep2View.as_view(), name='profile-step2'),
]

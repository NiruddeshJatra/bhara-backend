from rest_framework.routers import DefaultRouter

from rentals.views import RentalViewSet

router = DefaultRouter()
router.register(r'', RentalViewSet, basename='rental')

urlpatterns = router.urls

from rest_framework.routers import DefaultRouter

from listings.views import ProductViewSet

router = DefaultRouter()
router.register('', ProductViewSet, basename='listings')

urlpatterns = router.urls

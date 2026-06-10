from .celery import app as celery_app
__all__ = ('celery_app',)  # Ensures Celery is initialized when Django starts up

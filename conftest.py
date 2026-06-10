import pytest
from django.conf import settings


def pytest_configure():
    settings.DJANGO_SETTINGS_MODULE = 'core.settings.development'

@pytest.fixture(scope='session')
def django_db_setup():
  """Set up test database."""
  pass


@pytest.fixture
def api_client():
  """Return API client for testing."""
  from django.test import Client
  return Client()

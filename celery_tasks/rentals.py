from celery import shared_task
from services.sms import sms_service
import logging

logger = logging.getLogger('celery.rentals')


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_rental_request_sms(self, phone_number, product_title):
  """
  Notifies the owner that a new rental request arrived (owner-side only — D6
  exception approved pre-deployment). product_title arrives pre-truncated.
  Retries up to 3 times with 30-second delay on failure.
  """
  message = (
    f"Bhara: আপনার '{product_title}' এর জন্য নতুন ভাড়ার অনুরোধ এসেছে। "
    f"দেখুন: bhara.xyz"
  )
  try:
    result = sms_service.send(phone_number, message)
  except Exception as exc:
    logger.exception('Rental request SMS raised for %s', phone_number)
    raise self.retry(exc=exc)
  if not result.get('success'):
    logger.error('Rental request SMS failed for %s: %s', phone_number, result.get('error'))
    raise self.retry(exc=Exception(result.get('error', 'SMS send failed')))

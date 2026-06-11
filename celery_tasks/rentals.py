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
  result = sms_service.send(phone_number, message)
  if not result['success']:
    logger.error(f'Rental request SMS failed for {phone_number}')
    raise self.retry(exc=Exception(result.get('error', 'SMS send failed')))

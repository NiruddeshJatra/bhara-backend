from celery import shared_task
from services.sms import sms_service
import logging

logger = logging.getLogger('celery.users')


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_otp_task(self, phone_number, otp, purpose):
  """
  Sends OTP SMS asynchronously.
  purpose: 'signup' | 'password_reset'
  Retries up to 3 times with 30-second delay on failure.
  """
  if purpose == 'signup':
    message = f'Your Bhara signup OTP is: {otp}. Valid for 5 minutes. Do not share this code.'
  elif purpose == 'password_reset':
    message = f'Your Bhara password reset OTP is: {otp}. Valid for 5 minutes. Do not share this code.'
  else:
    message = f'Your Bhara OTP is: {otp}. Valid for 5 minutes.'

  result = sms_service.send(phone_number, message)
  if not result['success']:
    logger.error(f'OTP SMS failed for {phone_number}, purpose={purpose}')
    raise self.retry(exc=Exception(result.get('error', 'SMS send failed')))

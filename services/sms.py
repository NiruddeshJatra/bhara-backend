import requests
from django.conf import settings
import logging

logger = logging.getLogger('sms')


class AlphaSMSService:
  BASE_URL = 'https://api.sms.net.bd'

  def send(self, phone_number, message):
    """
    Sends SMS via Alpha SMS API.
    In DEBUG mode or when ALPHA_SMS_ENABLED=False, logs instead of sending.
    phone_number: BD format (01XXXXXXXXX)
    """
    if not getattr(settings, 'ALPHA_SMS_ENABLED', False):
      logger.info(f'[SMS MOCK] To: {phone_number} | Message: {message}')
      return {'success': True, 'mock': True}

    # Convert to international format
    recipient = '880' + phone_number[1:]  # 01712345678 -> 8801712345678

    try:
      response = requests.get(
        f'{self.BASE_URL}/sendsms',
        params={
          'api_key': settings.ALPHA_SMS_API_KEY,
          'msg': message,
          'to': recipient,
        },
        timeout=10
      )
      data = response.json()
      if data.get('error') == 0:
        logger.info(f'SMS sent to {phone_number}, request_id={data["data"]["request_id"]}')
        return {'success': True, 'request_id': data['data']['request_id']}
      else:
        logger.error(f'SMS failed: error={data.get("error")}, msg={data.get("msg")}')
        return {'success': False, 'error': data.get('msg')}
    except Exception as e:
      logger.exception(f'SMS exception: {e}')
      return {'success': False, 'error': str(e)}


sms_service = AlphaSMSService()

from rest_framework.response import Response
from rest_framework import status


def success_response(data=None, message='', status_code=status.HTTP_200_OK):
  return Response({
    'success': True,
    'message': message,
    'data': data or {},
  }, status=status_code)


def error_response(data=None, message='', status_code=status.HTTP_400_BAD_REQUEST):
  return Response({
    'success': False,
    'message': message,
    'data': data or {},
  }, status=status_code)

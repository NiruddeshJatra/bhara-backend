from PIL import Image
from io import BytesIO
from django.core.files.uploadedfile import InMemoryUploadedFile
import sys


def compress_image(uploaded_file, max_width, max_height, quality=85):
  """
  Compresses and resizes an uploaded image.
  Converts to JPEG. Returns a new InMemoryUploadedFile.

  Args:
    uploaded_file: Django uploaded file object
    max_width: int, max width in pixels
    max_height: int, max height in pixels
    quality: int, JPEG quality (1-95)

  Returns:
    InMemoryUploadedFile ready to assign to an ImageField
  """
  img = Image.open(uploaded_file)

  # Convert to RGB (handles PNG with transparency, CMYK, etc.)
  if img.mode != 'RGB':
    img = img.convert('RGB')

  # Resize maintaining aspect ratio, only if larger than max
  img.thumbnail((max_width, max_height), Image.LANCZOS)

  output = BytesIO()
  img.save(output, format='JPEG', quality=quality, optimize=True)
  output.seek(0)

  return InMemoryUploadedFile(
    output,
    'ImageField',
    f'{uploaded_file.name.rsplit(".", 1)[0]}.jpg',
    'image/jpeg',
    sys.getsizeof(output),
    None
  )

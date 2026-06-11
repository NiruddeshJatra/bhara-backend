# Installation Guide

## Prerequisites

- Python 3.9+
- PostgreSQL 12+
- Redis 6+
- Git

## 1. Setup Environment

### Clone the repository
```bash
git clone <repository-url>
cd bhara-backend
```

### Create virtual environment
```bash
# Using venv
python -m venv venv

# Activate on Windows
venv\Scripts\activate

# Activate on Linux/Mac
source venv/bin/activate
```

### Install dependencies
```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## 2. Database Setup

### Install PostgreSQL
- **Windows**: Download from https://www.postgresql.org/download/windows/
- **Mac**: `brew install postgresql`
- **Ubuntu**: `sudo apt-get install postgresql postgresql-contrib`

### Create database
```sql
CREATE DATABASE bhara;
CREATE USER bhara_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE bhara TO bhara_user;
```

### Configure environment variables
```bash
cp .env.example .env
```

Edit `.env` file:
```env
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DB_NAME=bhara
DB_USER=bhara_user
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432

# Redis
REDIS_URL=redis://127.0.0.1:6379/1

# SMS (optional for development)
ALPHA_SMS_API_KEY=

# AWS (optional for development)
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_STORAGE_BUCKET_NAME=
AWS_S3_REGION_NAME=ap-southeast-1
```

## 3. Redis Setup

### Option 1: Docker (Recommended)
```bash
docker-compose up -d
```

### Option 2: Local Installation
- **Windows**: Download from https://redis.io/download
- **Mac**: `brew install redis`
- **Ubuntu**: `sudo apt-get install redis-server`

Start Redis:
```bash
redis-server
```

## 4. Django Setup

### Run migrations
```bash
python manage.py migrate
```

### Create superuser
```bash
python manage.py createsuperuser
```

### Collect static files (for production)
```bash
python manage.py collectstatic
```

## 5. Running the Application

### Development server
```bash
python manage.py runserver
```

The API will be available at: http://localhost:8000

### Start Celery worker (in separate terminal)
```bash
celery -A core worker --loglevel=info
```

### Start Celery beat (for scheduled tasks, optional)
```bash
celery -A core beat --loglevel=info
```

## 6. Testing

### Run all tests
```bash
pytest
```

### Run with coverage
```bash
pytest --cov=users --cov-report=html
```

### Run specific test file
```bash
pytest users/tests/test_models.py
```

### Run with verbose output
```bash
pytest -v
```

### Run specific test
```bash
pytest users/tests/test_views.py::OTPViewTest::test_otp_request_signup_success
```

## 7. API Testing

### Using curl examples

#### Request OTP
```bash
curl -X POST http://localhost:8000/api/auth/otp/request/ \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "01712345678", "purpose": "signup"}'
```

#### Verify OTP
```bash
curl -X POST http://localhost:8000/api/auth/otp/verify/ \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "01712345678", "otp": "111111", "purpose": "signup"}'
```

#### Complete Signup
```bash
curl -X POST http://localhost:8000/api/auth/signup/complete/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer EPHEMERAL_TOKEN" \
  -d '{"full_name": "John Doe", "password": "Testpass123", "marketing_consent": false}'
```

#### Login
```bash
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "01712345678", "password": "Testpass123"}'
```

## 8. Common Issues

### Permission denied on database
```bash
# Grant permissions in PostgreSQL
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO bhara_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO bhara_user;
```

### Redis connection error
```bash
# Check if Redis is running
redis-cli ping

# Should return: PONG
```

### Migration errors
```bash
# Reset migrations (will delete data)
python manage.py migrate users zero
python manage.py migrate

# Or fake initial migrations
python manage.py migrate users --fake
```

### Port already in use
```bash
# Kill process on port 8000 (Windows)
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Kill process on port 8000 (Linux/Mac)
lsof -ti:8000 | xargs kill -9
```

## 9. Production Deployment

### Environment variables for production
```env
DEBUG=False
SECRET_KEY=production-secret-key
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com

# Database (use production credentials)
DB_NAME=bhara_prod
DB_USER=bhara_prod_user
DB_PASSWORD=production_password
DB_HOST=your-db-host
DB_PORT=5432

# AWS S3 for file storage
AWS_ACCESS_KEY_ID=your-aws-key
AWS_SECRET_ACCESS_KEY=your-aws-secret
AWS_STORAGE_BUCKET_NAME=your-bucket-name
AWS_S3_REGION_NAME=ap-southeast-1

# Enable real SMS
ALPHA_SMS_ENABLED=True
ALPHA_SMS_API_KEY=your-alpha-sms-key

# CORS for frontend
CORS_ALLOWED_ORIGINS=https://your-frontend-domain.com
```

### Production server setup
```bash
# Using gunicorn
pip install gunicorn
gunicorn core.wsgi:application --bind 0.0.0.0:8000

# Using systemd for auto-restart
# Create /etc/systemd/system/bhara-backend.service
```

## 10. Development Tips

### Django shell
```bash
python manage.py shell
```

### Check database schema
```bash
python manage.py showmigrations
python manage.py sqlmigrate users 0001
```

### Debug Celery
```bash
celery -A core worker --loglevel=debug
```

### Monitor Redis
```bash
redis-cli monitor
```

### Create test data
```python
# In Django shell
from users.tests.factories import UserFactory, VerifiedUserFactory
user = UserFactory()
verified_user = VerifiedUserFactory()
```

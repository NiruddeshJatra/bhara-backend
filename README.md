# Bhara Backend

Peer-to-peer rental platform backend for Bangladesh.

## Features

- **Authentication**: Phone number + password with OTP verification
- **User Trust System**: Three-tier verification (unverified, verified, partner)
- **Profile Completion**: Two-step profile setup with document verification
- **Image Compression**: Automatic compression for uploaded images
- **SMS Integration**: Alpha SMS for OTP delivery
- **JWT Tokens**: Access and refresh token system with httpOnly cookies
- **Rate Limiting**: Login attempt lockout protection
- **Admin Dashboard**: User management and approval system

## Tech Stack

- **Framework**: Django 5.x with Django REST Framework
- **Database**: PostgreSQL
- **Cache**: Redis
- **Queue**: Celery with Redis broker
- **Authentication**: JWT with simplejwt
- **File Storage**: Local (dev) / AWS S3 (prod)
- **SMS**: Alpha SMS API
- **Testing**: pytest with factory_boy

## Quick Start

1. **Clone and setup**
   ```bash
   git clone <repository-url>
   cd bhara-backend
   cp .env.example .env
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

3. **Setup Redis**
   ```bash
   docker-compose up -d
   ```

4. **Run migrations**
   ```bash
   python manage.py migrate
   ```

5. **Create superuser**
   ```bash
   python manage.py createsuperuser
   ```

6. **Start development server**
   ```bash
   python manage.py runserver
   ```

7. **Start Celery worker** (in separate terminal)
   ```bash
   celery -A core worker --loglevel=info
   ```

## Environment Variables

See `.env.example` for required environment variables:

- `SECRET_KEY`: Django secret key
- `DEBUG`: Enable debug mode
- `ALLOWED_HOSTS`: Comma-separated list of allowed hosts
- `REDIS_URL`: Redis connection URL
- `ALPHA_SMS_API_KEY`: Alpha SMS API key
- `DB_*`: Database connection settings
- `AWS_*`: S3 storage settings (production)

## API Endpoints

### Authentication
- `POST /api/auth/otp/request/` - Request OTP
- `POST /api/auth/otp/verify/` - Verify OTP
- `POST /api/auth/signup/complete/` - Complete signup
- `POST /api/auth/login/` - Login
- `POST /api/auth/logout/` - Logout
- `POST /api/auth/token/refresh/` - Refresh access token
- `POST /api/auth/password-reset/complete/` - Complete password reset

### User Profile
- `GET /api/users/profile/` - Get user profile
- `PATCH /api/users/profile/` - Update full name
- `PATCH /api/users/profile/step1/` - Complete profile step 1
- `POST /api/users/profile/step2/` - Submit identity documents

## Testing

Run tests with pytest:
```bash
pytest
```

Run with coverage:
```bash
pytest --cov=users --cov-report=html
```

## Development Notes

### OTP in Development
In DEBUG mode, OTP is always hardcoded to `111111`. No actual SMS is sent.

### Image Compression
- Profile pictures: Max 800×800px, JPEG quality 85
- ID images: Max 1200×900px, JPEG quality 90

### Login Lockout
5 consecutive failed attempts → 15-minute lockout

### Trust Levels
- `unverified`: Can browse listings only
- `verified`: Can rent and list items (with completed profile)
- `partner`: Same as verified + special badge

## License

[Add your license information here]

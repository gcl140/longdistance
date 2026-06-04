from pathlib import Path
import os
from dotenv import load_dotenv
load_dotenv()


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv(
    'DJANGO_SECRET_KEY',
    'django-insecure-g(^epjdhu+9a-mlbnt%xl%_ta3tk8k=m$nop#-at%7@&)#2dwe',
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'True') == 'True'

# Comma-separated env list, e.g. "lisa.mydomain.com,127.0.0.1"
ALLOWED_HOSTS = [h.strip() for h in os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if h.strip()]

# Behind Cloudflare Tunnel / any HTTPS proxy, trust the public origin for CSRF + WebSockets.
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.getenv('CSRF_TRUSTED_ORIGINS', '').split(',') if o.strip()]
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


# Application definition

INSTALLED_APPS = [
    'daphne',  # must precede staticfiles so runserver serves ASGI (WebSockets)
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'channels',
    'social_django',
    "yuzzaz",
    "friends",
    "parties",
    "catalog",
    "schedule",
    "notifications",
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'longdistance.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'catalog.context_processors.request_quota',
            ],
        },
    },
]

WSGI_APPLICATION = 'longdistance.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

# Postgres in production (set POSTGRES_DB); SQLite for local dev otherwise.
if os.getenv('POSTGRES_DB'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('POSTGRES_DB'),
            'USER': os.getenv('POSTGRES_USER', 'postgres'),
            'PASSWORD': os.getenv('POSTGRES_PASSWORD', ''),
            'HOST': os.getenv('POSTGRES_HOST', '127.0.0.1'),
            'PORT': os.getenv('POSTGRES_PORT', '5432'),
            'CONN_MAX_AGE': 60,
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'yuzzaz.CustomUser'

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER')  # Use your Gmail address here
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD')  # Use the app password (not your Google account password)
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER  # From header must match the authenticated Gmail account

# Where new movie-request alerts are sent (the person who sources the file).
MOVIE_REQUEST_NOTIFY_EMAIL = os.getenv('MOVIE_REQUEST_NOTIFY_EMAIL', 'gftinity01@gmail.com')
# Template for the "go get it" link in those alerts ({query} = "Title Year").
TORRENT_SEARCH_URL = os.getenv('TORRENT_SEARCH_URL', 'https://1337x.to/search/{query}/1/')
# Fulfilled/closed requests are auto-purged this many days after being reviewed.
MOVIE_REQUEST_RETENTION_DAYS = int(os.getenv('MOVIE_REQUEST_RETENTION_DAYS', '14'))


# Google OAuth2 keys (now from environment)
SOCIAL_AUTH_GOOGLE_OAUTH2_KEY = os.getenv('GOOGLE_OAUTH2_KEY')
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = os.getenv('GOOGLE_OAUTH2_SECRET')

AUTHENTICATION_BACKENDS = (
    'social_core.backends.google.GoogleOAuth2',
    'django.contrib.auth.backends.ModelBackend',
)

# Optional (to handle missing email cases)
SOCIAL_AUTH_GOOGLE_OAUTH2_SCOPE = [
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
]

MEDIA_URL = '/media/' 
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

STATIC_URL = '/static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, "static")]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = 'login'
LOGIN_URL = 'login'

SOCIAL_AUTH_GOOGLE_OAUTH2_SCOPE = ['email', 'profile']


SOCIAL_AUTH_PIPELINE = (
    'social_core.pipeline.social_auth.social_details',
    'social_core.pipeline.social_auth.social_uid',
    'forum.pipeline.prevent_duplicate_social_auth',  # ✅ Here
    'social_core.pipeline.social_auth.auth_allowed',
    'social_core.pipeline.social_auth.social_user',
    'social_core.pipeline.user.get_username',
    'social_core.pipeline.user.create_user',
    'forum.pipeline.save_user_details',  # where you set is_parent, etc.
    'social_core.pipeline.social_auth.associate_user',
    'social_core.pipeline.social_auth.load_extra_data',
    'social_core.pipeline.user.user_details',
)

RECAPTCHA_PUBLIC_KEY = os.getenv('SITE_KEY')
RECAPTCHA_PRIVATE_KEY = os.getenv('SECRET_KEY')
SILENCED_SYSTEM_CHECKS = ['captcha.recaptcha_test_key_error']
RECAPTCHA_REQUIRED_SCORE = 0.5


# ---- Channels / WebSockets ----
ASGI_APPLICATION = 'longdistance.asgi.application'

# Dev defaults to an in-memory layer (single-process, no Redis needed).
# In production set REDIS_URL to use channels-redis across processes.
REDIS_URL = os.getenv('REDIS_URL')
if REDIS_URL:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {'hosts': [REDIS_URL]},
        }
    }
else:
    CHANNEL_LAYERS = {
        'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}
    }


# ---- TMDb (movie metadata) ----
# Get a free key at https://www.themoviedb.org/settings/api
TMDB_API_KEY = os.getenv('TMDB_API_KEY', '')
TMDB_IMAGE_BASE = 'https://image.tmdb.org/t/p/w500'        # posters (portrait, small)
TMDB_BACKDROP_BASE = 'https://image.tmdb.org/t/p/w1280'    # backdrops (wide, HD hero)

# ---- Movie-request quota ----
# Per-user storage budget. Admins (is_staff) are exempt; see catalog/quota.py.
REQUEST_QUOTA_MB = int(os.getenv('REQUEST_QUOTA_MB', 5 * 1024))     # 5 GB
REQUEST_SIZE_MB_PER_MIN = int(os.getenv('REQUEST_SIZE_MB_PER_MIN', 20))
REQUEST_SIZE_FALLBACK_MB = int(os.getenv('REQUEST_SIZE_FALLBACK_MB', 1500))
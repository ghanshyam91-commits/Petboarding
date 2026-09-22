import os
from pathlib import Path
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("SECRET_KEY is required outside local development")
    SECRET_KEY = "local-development-only-never-deploy"
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
CSRF_TRUSTED_ORIGINS = [
    x for x in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if x
]
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "care",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {
    "default": dj_database_url.config(
        default=f'sqlite:///{BASE_DIR / "db.sqlite3"}', conn_max_age=60
    )
}
if not DEBUG and DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
    raise RuntimeError("Production requires PostgreSQL for capacity locking")
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]
LANGUAGE_CODE = "en-in"
LANGUAGES = [
    ("en", "English"),
    ("hi", "Hindi"),
    ("kn", "Kannada"),
    ("ta", "Tamil"),
    ("te", "Telugu"),
    ("mr", "Marathi"),
    ("bn", "Bengali"),
]
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/login/"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
MIDDLEWARE.insert(
    MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware"),
    "care.middleware.LoginThrottle",
)
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024

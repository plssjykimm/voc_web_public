import os
from pathlib import Path

from django.core.management.utils import get_random_secret_key

BASE_DIR = Path(__file__).resolve().parent.parent
LOCAL = BASE_DIR / "local"
PRODUCTION = bool(os.environ.get("POSTGRES_HOST"))
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if PRODUCTION:
        raise RuntimeError("DJANGO_SECRET_KEY is required")
    LOCAL.mkdir(exist_ok=True)
    keyfile = LOCAL / "django.key"
    if not keyfile.exists():
        with keyfile.open("x") as stream:
            stream.write(get_random_secret_key())
    SECRET_KEY = keyfile.read_text()
DEBUG = not PRODUCTION
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",")
INSTALLED_APPS = [
    "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions",
    "django.contrib.messages", "django.contrib.staticfiles", "voc",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware", "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware", "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request", "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
if PRODUCTION:
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql", "HOST": os.environ["POSTGRES_HOST"],
        "NAME": os.environ["POSTGRES_DB"], "USER": os.environ["POSTGRES_USER"],
        "PASSWORD": os.environ["POSTGRES_PASSWORD"], "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }}
else:
    LOCAL.mkdir(exist_ok=True)
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": LOCAL / "voc.sqlite3",
                             "OPTIONS": {"timeout": 15, "transaction_mode": "IMMEDIATE"}}}
AUTH_USER_MODEL = "voc.User"
LOGIN_URL = "/login"
LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", LOCAL / "attachments"))
VOC_MAX_FILE_SIZE = int(os.environ.get("VOC_MAX_FILE_SIZE", 20 * 1024 * 1024))
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = PRODUCTION
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

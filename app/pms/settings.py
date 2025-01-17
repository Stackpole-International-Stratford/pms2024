"""
Django settings for pms project.

Generated by 'django-admin startproject' using Django 4.1.2.

For more information on this file, see
https://docs.djangoproject.com/en/4.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/4.1/ref/settings/
"""

import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY', 'changeme')

# SECURITY WARNING: don't run with debug turned on in production!
# DEBUG = bool(int(os.environ.get('DEBUG', 0)))
DEBUG = True

ALLOWED_HOSTS = ['10.5.1.131','pmdsdata12', '10.4.1.234', '127.0.0.1',
                 'localhost', '10.4.1.234', '10.4.1.232', 'pmdsdata9']
ALLOWED_HOSTS_ENV = os.environ.get('ALLOWED_HOSTS')
if ALLOWED_HOSTS_ENV:
    ALLOWED_HOSTS.extend(ALLOWED_HOSTS_ENV.split(','))

# Application definition

# def show_toolbar(request):
#     return True
# SHOW_TOOLBAR_CALLBACK = show_toolbar
# DEBUG_TOOLBAR_CONFIG = {'INSERT_BEFORE':'</head>'}
INTERNAL_IPS = ['pmdsdata12', '10.4.1.234', '127.0.0.1',
                 'localhost', '10.4.1.232']
# DEBUG_TOOLBAR_CONFIG = {
#     'SHOW_TOOLBAR_CALLBACK': lambda _request: DEBUG
# }

INSTALLED_APPS = [
    'whitenoise.runserver_nostatic',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'debug_toolbar',
    'django_bootstrap5',
    'widget_tweaks',
    'corsheaders',
    'prod_query',
    'barcode',
    'dashboards',
    'site_variables',
    'query_tracking',
    'plant',
    'quality',
    'forms',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    # 'pms.middleware.timezone.TimezoneMiddleware',
    'pms.middleware.site_variables.SiteVariableMiddleware',
    'barcode.middleware.CheckUnlockCodeMiddleware',
    'barcode.middleware.SupervisorLockoutMiddleware',



]
if DEBUG:
    MIDDLEWARE.remove('whitenoise.middleware.WhiteNoiseMiddleware')


ROOT_URLCONF = 'pms.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'pms/templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'pms.wsgi.application'


# Database
# https://docs.djangoproject.com/en/4.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ.get('DB_PMS_NAME', 'django_pms'),
        'USER': os.environ.get('DB_PMS_USER', 'muser'),
        'PASSWORD': os.environ.get('DB_PMS_PASSWORD', 'wsj.231.kql'),
        'HOST': os.environ.get('DB_PMS_HOST', '10.4.1.245'),
        'PORT': os.environ.get('DB_PMS_PORT', 6601),
    },
    'prodrpt-md': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ.get('DB_PRDRPT_NAME', 'prodrptdb'),
        'USER': os.environ.get('DB_PRDRPT_USER', 'stuser'),
        'PASSWORD': os.environ.get('DB_PRDRPT_PASSWORD', 'stp383'),
        'HOST': os.environ.get('DB_PRDRPT_HOST', '10.4.1.245'),
        'PORT': os.environ.get('DB_PRDRPT_PORT', 3306),
    },
}




# CACHES = {
#     "default": {
#         "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
#         "LOCATION": "/var/tmp/django_cache",
#     }
# }

# Password validation
# https://docs.djangoproject.com/en/4.1/ref/settings/#auth-password-validators

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
# https://docs.djangoproject.com/en/4.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'America/Toronto'

USE_I18N = True

USE_TZ = True




# Boostrap5 settings
BOOTSTRAP5 = {

    # The complete URL to the Bootstrap CSS file.
    # Note that a URL can be either a string
    # ("https://stackpath.bootstrapcdn.com/bootstrap/4.1.1/css/bootstrap.min.css"),
    # or a dict with keys `url`, `integrity` and `crossorigin` like the default value below.
    "css_url": "http://pmdsdata12/static/static/bootstrap/css/bootstrap.min.css",

    # The complete URL to the Bootstrap bundle JavaScript file.
    "javascript_url": "http://pmdsdata12/static/static/bootstrap/js/bootstrap.bundle.min.js",

    # The complete URL to the Bootstrap CSS theme file (None means no theme).
    "theme_url": None,

    # Put JavaScript in the HEAD section of the HTML document (only relevant if you use bootstrap5.html).
    'javascript_in_head': False,

    # Wrapper class for non-inline fields.
    # The default value "mb-3" is the spacing as used by Bootstrap 5 example code.
    'wrapper_class': 'mb-3',

    # Wrapper class for inline fields.
    # The default value is empty, as Bootstrap5 example code doesn't use a wrapper class.
    'inline_wrapper_class': '',

    # Label class to use in horizontal forms.
    'horizontal_label_class': 'col-sm-2',

    # Field class to use in horizontal forms.
    'horizontal_field_class': 'col-sm-10',

    # Field class used for horizontal fields withut a label.
    'horizontal_field_offset_class': 'offset-sm-2',

    # Set placeholder attributes to label if no placeholder is provided.
    'set_placeholder': True,

    # Class to indicate required field (better to set this in your Django form).
    'required_css_class': '',

    # Class to indicate field has one or more errors (better to set this in your Django form).
    'error_css_class': '',

    # Class to indicate success, meaning the field has valid input (better to set this in your Django form).
    'success_css_class': '',

    # Enable or disable Bootstrap 5 server side validation classes (separate from the indicator classes above).
    'server_side_validation': True,

    # Renderers (only set these if you have studied the source and understand the inner workings).
    'formset_renderers':{
        'default': 'django_bootstrap5.renderers.FormsetRenderer',
    },
    'form_renderers': {
        'default': 'django_bootstrap5.renderers.FormRenderer',
    },
    'field_renderers': {
        'default': 'django_bootstrap5.renderers.FieldRenderer',
    },
}


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.1/howto/static-files/

STATIC_URL = '/static/static/'
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media_files')

STATIC_ROOT = BASE_DIR / 'static_files'

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'common_static'),
]

# Default primary key field type
# https://docs.djangoproject.com/en/4.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CORS_ALLOW_ALL_ORIGINS = True

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'file': {
            'format': '%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
        },
    },
    'filters': {
        'require_debug_true': {
            '()': 'django.utils.log.RequireDebugTrue',
        }
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'filters': ['require_debug_true'],
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        # 'django.db.backends': {
        #     'level': 'DEBUG',
        #     'handlers': ['console'],
        # },
        'django.request': {
            'level': 'INFO',
            'handlers': ['console',]
        },
        'prod-query': {
            'level': 'INFO',
            'handlers': ['console',],
        }

    }
}


EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp01.stackpole.ca'
EMAIL_PORT = 25  # Default SMTP port
EMAIL_USE_TLS = False
EMAIL_USE_SSL = False
DEFAULT_FROM_EMAIL = 'noreply@johnsonelectric.com'


# Email groups
EMAIL_GROUPS = {
    'Factory_Focus_Leaders': [
        'dave.milne@johnsonelectric.com',
        'joel.langford@johnsonelectric.com',
        'dave.clark@johnsonelectric.com',
    ],
    'Supervisor_Leads': [
        'ken.frey@johnsonelectric.com',
        'brian.joiner@johnsonelectric.com',
        'gary.harvey@johnsonelectric.com'
    ],
    'Supervisors': [
        'andrew.smith@johnsonelectric.com',
        'saurabh.bhardwaj@johnsonelectric.com',
        'paul.currie@johnsonelectric.com',
        'andrew.terpstra@johnsonelectric.com',
        'evan.george@johnsonelectric.com',
        'david.mclaren@johnsonelectric.com',
        'robert.tupy@johnsonelectric.com',
        'scott.brownlee@johnsonelectric.com',
        'shivam.bhatt@johnsonelectric.com',
        'jamie.pearce@johnsonelectric.com'
    ],
    'Backup_Supervisors': [
        'mark.morse@johnsonelectric.com'
    ],
    'Team_Leads': [
        'nathan.klein-geitink@johnsonelectric.com',
        'lisa.baker@johnsonelectric.com',
        'geoff.goldsack@johnsonelectric.com'
    ],
    'Quality': [
        'geoff.perrier@johnsonelectric.com'
    ],
    'Testing_group': [
        'tyler.careless@johnsonelectric.com',
        # 'chris.strutton@johnsonelectric.com',
    ],
    #     'Testing_group': [
    #     'tyler.careless@johnsonelectric.com',
    #     'chris.strutton@johnsonelectric.com',
    # ]
}

import MySQLdb
def get_db_connection():
    return MySQLdb.connect(
        host="10.4.1.224",
        user="stuser",
        passwd="stp383",
        db="prodrptdb"
    )
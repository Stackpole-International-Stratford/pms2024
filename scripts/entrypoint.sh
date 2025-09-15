#!/bin/sh

set -e

# Remove this to see if we can put it in Dockerfile instead. This being done at build time rather than runtime will make the deployment have less downtime
# python manage.py collectstatic --noinput

# uwsgi --socket :8000 --master --enable-threads --module pms.wsgi 

uwsgi --http 0.0.0.0:80 --master --module pms.wsgi --processes 4 --static-map /media=/app/media_files 

FROM python:3.9-alpine

ENV PATH="/scripts:${PATH}"

# need to add zscaler cert to image for apk to work
# https://stackoverflow.com/a/70087108/24651730

COPY ./trusted-certs.pem /usr/local/share/ca-certificates/
RUN cat /usr/local/share/ca-certificates/trusted-certs.pem >> /etc/ssl/certs/ca-certificates.crt

COPY ./requirements.txt /requirements.txt
RUN apk add --no-cache mariadb-connector-c openldap pango cairo gdk-pixbuf libffi shared-mime-info fontconfig ttf-dejavu
# Build the font cache manually because Alpine might skip the automatic step to refresh the list of fonts after installing ttf-dejavu. prevents segfaults from weasyprint/pango looking for fonts
RUN fc-cache -f
RUN apk add --update --no-cache --virtual .tmp gcc libc-dev linux-headers mariadb-connector-c-dev build-base openldap-dev python3-dev cairo-dev pango-dev gdk-pixbuf-dev libffi-dev
RUN python -m pip install --upgrade pip
RUN pip install -r /requirements.txt
RUN apk del .tmp

RUN mkdir /app
COPY ./app /app
WORKDIR /app

# These 2 packages are automagically installed as dependencies for weasyprint (pdf lib).... but they compress and cause massive un-needed slowdown of build process
RUN pip uninstall -y zopfli Brotli

# collect static files at build time
RUN python manage.py collectstatic --noinput

COPY ./scripts /scripts
RUN chmod +x /scripts/*

RUN adduser -D user

EXPOSE 8000

CMD [ "entrypoint.sh" ]


# docker build -t <name> .
# docker run -d --restart unless-stopped --name <imagename> -p <portyouwannaexpose>:80 <containername>
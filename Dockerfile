FROM python:3.9-alpine

ENV PATH="/scripts:${PATH}"

# need to add zscaler cert to image for apk to work
# https://stackoverflow.com/a/70087108/24651730

COPY ./trusted-certs.pem /usr/local/share/ca-certificates/
RUN cat /usr/local/share/ca-certificates/trusted-certs.pem >> /etc/ssl/certs/ca-certificates.crt

COPY ./requirements.txt /requirements.txt
RUN apk add --no-cache mariadb-connector-c openldap
RUN apk add --update --no-cache --virtual .tmp gcc libc-dev linux-headers mariadb-connector-c-dev build-base openldap-dev python3-dev
RUN python -m pip install --upgrade pip
RUN pip install -r /requirements.txt
RUN apk del .tmp

RUN mkdir /app
COPY ./app /app
WORKDIR /app
COPY ./scripts /scripts
RUN chmod +x /scripts/*

RUN adduser -D user

EXPOSE 8000

CMD [ "entrypoint.sh" ]


# docker build -t <name> .
# docker run -d --restart unless-stopped --name <imagename> -p <portyouwannaexpose>:80 <containername>
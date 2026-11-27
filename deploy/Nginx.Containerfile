FROM docker.io/library/nginx:stable-alpine
COPY static/ /usr/share/nginx/html/static/
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf

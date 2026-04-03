#!/bin/sh
# Replace environment variables in nginx config
envsubst '${PORT} ${BACKEND_URL}' < /etc/nginx/nginx.conf.template > /etc/nginx/conf.d/default.conf
# Start nginx
nginx -g 'daemon off;'

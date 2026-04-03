#!/bin/sh
# Get DNS resolver from container
export DNS_RESOLVER=$(grep nameserver /etc/resolv.conf | head -1 | awk '{print $2}')
# Replace environment variables in nginx config
envsubst '${PORT} ${BACKEND_URL} ${DNS_RESOLVER}' < /etc/nginx/nginx.conf.template > /etc/nginx/conf.d/default.conf
# Start nginx
nginx -g 'daemon off;'

#!/bin/sh
set -eu
python manage.py migrate --noinput
if [ "${ENABLE_DEMO_LOGIN:-false}" = "true" ]; then
    python manage.py seed_public_demo
fi

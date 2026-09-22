#!/usr/bin/env bash
set -euo pipefail

# Free web services do not support Render's pre-deploy command.
# Fail startup if migrations fail; never serve against a partial schema.
python manage.py migrate --noinput
exec python -m gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-10000}" \
  --workers "${WEB_CONCURRENCY:-1}" --threads 2 \
  --access-logfile - --error-logfile -

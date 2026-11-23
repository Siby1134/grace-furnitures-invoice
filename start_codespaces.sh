#!/usr/bin/env bash
set -e
export PORT="${PORT:-5050}"
export ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-Grace@2026}"
export SECRET_KEY="${SECRET_KEY:-codespaces-change-this-secret}"
python app.py

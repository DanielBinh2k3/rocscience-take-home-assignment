#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."

if [[ "$1" == http* ]] && [[ -n "$2" ]]; then
  HOST="$1"
  MESSAGE="$2"
else
  HOST="http://localhost:8000"
  MESSAGE="${1:-hello}"
fi

curl -s -N -X POST "$HOST/api/v1/chat/stream" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11\", \"user_id\": \"user-123\", \"message\": \"$MESSAGE\"}"

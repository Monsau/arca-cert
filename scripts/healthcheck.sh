#!/usr/bin/env bash
# Kubernetes probe script.
set -euo pipefail
PORT="${PORT:-8093}"
curl -fsS "http://localhost:${{PORT}}/healthz" > /dev/null

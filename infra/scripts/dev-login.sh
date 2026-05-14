#!/usr/bin/env bash
# AEGIS dev login helper.
#
# Fetches a JWT from the dev Keycloak realm using the resource-owner-password
# grant and prints both the raw token and the sessionStorage snippet to paste
# in the browser DevTools console.
#
# Usage:
#   ./infra/scripts/dev-login.sh                       # default admin@aegis.local / admin
#   ./infra/scripts/dev-login.sh user@example.com pw   # custom user
#
# Requires: curl, python3 (for JSON parsing).

set -euo pipefail

USER_NAME=${1:-admin@aegis.local}
PASSWORD=${2:-admin}
KEYCLOAK_URL=${KEYCLOAK_URL:-http://localhost:8080}
REALM=${REALM:-aegis}
CLIENT_ID=${CLIENT_ID:-aegis-web}

resp=$(curl -sS -X POST \
  "${KEYCLOAK_URL}/realms/${REALM}/protocol/openid-connect/token" \
  -d "grant_type=password" \
  -d "client_id=${CLIENT_ID}" \
  -d "username=${USER_NAME}" \
  -d "password=${PASSWORD}")

if ! echo "$resp" | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if 'access_token' in d else 1)"; then
  echo "❌ Keycloak rejected the login. Full response:" >&2
  echo "$resp" >&2
  exit 1
fi

token=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

cat <<EOF
✅ Token obtained for ${USER_NAME}

Paste this in the browser DevTools console on http://localhost:5173 :

  sessionStorage.setItem('aegis.token', '${token}');
  location.reload();

Or use it with curl:

  export AEGIS_TOKEN='${token}'
  curl -H "Authorization: Bearer \$AEGIS_TOKEN" http://localhost:8000/v1/me

Decoded payload (jq optional):
EOF
echo "$token" | python3 -c "
import sys, base64, json
parts = sys.stdin.read().strip().split('.')
pad = '=' * (-len(parts[1]) % 4)
print(json.dumps(json.loads(base64.urlsafe_b64decode(parts[1] + pad)), indent=2))
"

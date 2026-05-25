#!/bin/bash
# eval-org-007: Digest sanitization — secrets must not survive output
set -uo pipefail

CABINET_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"

SAMPLE_FILE=$(mktemp /tmp/eval-org-007-sample-XXXXXX.json)
CONFIG_FILE=$(mktemp /tmp/eval-org-007-config-XXXXXX.yml)
PRODUCT_FILE=$(mktemp /tmp/eval-org-007-product-XXXXXX.yml)
trap 'rm -f "$SAMPLE_FILE" "$CONFIG_FILE" "$PRODUCT_FILE"' EXIT

# Create a test product config with real names
cat > "$PRODUCT_FILE" << 'EOF'
product:
  name: AcmeApp
  captain_name: Alice
EOF

# Create a test sanitize config
cat > "$CONFIG_FILE" << 'EOF'
replacements: {}
patterns:
  api_key: '(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*\S+'
  env_var: '(?i)(DATABASE_URL|NEON_|TELEGRAM_BOT_TOKEN)\S*=\S+'
  bearer_token: '(?i)bearer\s+[a-zA-Z0-9._\-]+'
  connection_string: '(?i)(postgres|postgresql|redis)://[^\s]+'
sanitize_urls: true
strip_paths_beyond: "/opt/founders-cabinet"
sanitize_external_ids: true
id_patterns:
  uuid: '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
EOF

# Create sample data with secrets
cat > "$SAMPLE_FILE" << 'EOF'
[
  {
    "task_summary": "Connected AcmeApp to Neon database",
    "officer": "cto",
    "outcome": "success",
    "what_happened": "Used DATABASE_URL=postgres://admin:s3cret@db.neon.tech:5432/acme_prod",
    "lessons_learned": "Alice said to use api_key: sk-ant-abc123xyz for authentication. Bearer eyJhbGciOiJIUzI1NiJ9.test.sig was also tested."
  },
  {
    "task_summary": "Updated page 331412e2-7cc5-815c-b533-e18353773815 in Notion",
    "officer": "cos",
    "outcome": "success",
    "what_happened": "Fetched https://api.notion.com/v1/pages?secret=abc",
    "lessons_learned": "Read config from /opt/founders-cabinet/instance/config/product.yml"
  }
]
EOF

# Run the digest compiler with the test config — override CABINET_ROOT so product.yml
# is read from the temp location. We use a small Python wrapper to pass all paths.
OUTPUT=$(python3 -c "
import sys, os
sys.path.insert(0, os.path.join('$CABINET_ROOT', 'cabinet/scripts/lib'))
from compile_digest_lib import load_sanitize_config, load_records_from_sample, compile_digest

config = load_sanitize_config('$CONFIG_FILE', '$PRODUCT_FILE')
records = load_records_from_sample('$SAMPLE_FILE')
print(compile_digest(records, config, '2026-W22'))
" 2>/dev/null)
EXIT_CODE=$?

if [ "$EXIT_CODE" -ne 0 ]; then
    echo "FAIL: compile-digest failed (exit $EXIT_CODE)"
    exit 1
fi

FAILURES=0
check_absent() {
    if echo "$OUTPUT" | grep -qi "$1"; then
        echo "  FAIL: '$1' found in sanitized output"
        FAILURES=$((FAILURES + 1))
    fi
}

# Secrets must be stripped
check_absent "s3cret"
check_absent "sk-ant-abc123xyz"
check_absent "eyJhbGciOiJIUzI1NiJ9"
check_absent "331412e2-7cc5-815c"
check_absent "secret=abc"
check_absent "admin:s3cret"

# Product name and captain name must be replaced
check_absent "AcmeApp"
check_absent "Alice"

# Replacement markers must be present
if ! echo "$OUTPUT" | grep -q "\[PRODUCT\]"; then
    echo "  FAIL: Expected [PRODUCT] replacement marker"
    FAILURES=$((FAILURES + 1))
fi
if ! echo "$OUTPUT" | grep -q "\[CAPTAIN\]"; then
    echo "  FAIL: Expected [CAPTAIN] replacement marker"
    FAILURES=$((FAILURES + 1))
fi

if [ "$FAILURES" -gt 0 ]; then
    echo "FAIL: $FAILURES sanitization checks failed"
    exit 1
fi

echo "OK: All secrets stripped from digest output"
exit 0

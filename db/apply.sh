#!/usr/bin/env bash
# db/apply.sh — 简单 SQL 执行器（不引入 Flyway / Liquibase）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DB_DIR="$ROOT/db"
PSQL="${PSQL:-docker compose exec -T postgres psql -U admin -d realestate -v ON_ERROR_STOP=1}"

run_file() {
  local rel="$1"
  local path="$DB_DIR/$rel"
  [[ -f "$path" ]] || { echo "MISSING: $path"; exit 1; }
  echo "==> $rel"
  $PSQL -f "/data/repo/db/$rel"
}

case "${1:-}" in
  baseline)
    grep -v '^\s*#' "$DB_DIR/manifest.txt" | grep -v '^\s*$' | while read -r f; do
      run_file "$f"
    done
    ;;
  migration)
    [[ -n "${2:-}" ]] || { echo "Usage: $0 migration <filename>"; exit 1; }
    run_file "migrations/$2"
    ;;
  ops)
    [[ -n "${2:-}" ]] || { echo "Usage: $0 ops <fixes|cleanups|rollbacks>/<filename>"; exit 1; }
    echo "WARNING: ops scripts are manual-only. Review before running."
    run_file "ops/$2"
    ;;
  *)
    echo "Usage: $0 baseline | migration <file> | ops <path>"
    exit 1
    ;;
esac

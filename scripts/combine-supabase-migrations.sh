#!/usr/bin/env bash
# Concatenate Supabase migrations in dependency order for paste into SQL Editor (empty DB only).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/supabase/dist/all_migrations.sql"
mkdir -p "$(dirname "$OUT")"

FILES=(
  "20260428100000_init.sql"
  "20260429120000_performance_indexes.sql"
  "20260429120001_notifications.sql"
  "20260429120003_meetings_lead_optional.sql"
  "20260429120004_dashboard_metrics.sql"
  "20260429130000_brisk_ui_fields.sql"
)

{
  cat <<'EOF'
-- ============================================================================
-- Dracara Growth OS — COMBINED SQL (fresh Postgres / new Supabase project only)
-- ----------------------------------------------------------------------------
-- Do NOT run wholesale against a database that already applied these migrations.
-- Use incremental files under supabase/migrations/ for existing environments,
-- or reset the remote DB first.
--
-- Order: init → indexes → notifications → meetings FK tweak → dashboard RPC
--        → Brisk UI fields / marketing metrics.
-- ============================================================================

EOF
  for f in "${FILES[@]}"; do
    path="$ROOT/supabase/migrations/$f"
    if [[ ! -f "$path" ]]; then
      echo "Missing: $path" >&2
      exit 1
    fi
    echo ""
    echo "-- >>> BEGIN $f <<<"
    cat "$path"
    echo ""
    echo "-- >>> END $f <<<"
  done
} >"$OUT"

echo "Wrote $OUT"

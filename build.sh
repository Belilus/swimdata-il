#!/usr/bin/env bash
# Reproduce the whole project: extract -> load (both meets) -> exports.
#   ./build.sh [db_path]
set -euo pipefail
cd "$(dirname "$0")"
DB="${1:-build/isa.duckdb}"
mkdir -p build data/interim

echo "== meet 1: young-ages (two-source bilingual) =="
python3 src/run_pipeline.py --db "$DB"

SENIORS="samples/results_seniors_winter2025.pdf"
if [ -f "$SENIORS" ]; then
  echo "== meet 2: seniors (loglig Hebrew export) =="
  python3 src/extract_loglig.py "$SENIORS" -o data/interim/seniors_results.csv --year 2025
  python3 src/load_loglig.py --db "$DB" --csv data/interim/seniors_results.csv \
    --name-he 'אליפות ישראל "ארנה" נוער ובוגרים חורף 2025' \
    --name-en 'Arena Israel National Winter Championships - Youth & Seniors 2025' \
    --start 2025-12-23 --end 2025-12-27
else
  echo "(skip meet 2 -- $SENIORS not present; download via loglig export URL)"
fi

echo "== exports =="
python3 src/export_web.py       --db "$DB" --out web/data.js
python3 src/swimedge_adapter.py --db "$DB" --out web/swimedge_bundle.json
# single-file dashboard (data inlined) for easy sharing
python3 - <<'PY'
html=open("web/index.html",encoding="utf-8").read()
data=open("web/data.js",encoding="utf-8").read()
open("web/dashboard.html","w",encoding="utf-8").write(
    html.replace('<script src="data.js"></script>','<script>'+data+'</script>'))
print("  web/dashboard.html (single file) ready")
PY
echo "Done. Open web/dashboard.html (or web/index.html)."

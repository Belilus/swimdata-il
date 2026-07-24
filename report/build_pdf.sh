#!/usr/bin/env bash
# Build report/report.pdf from report/report.md (for Moodle submission).
set -euo pipefail
cd "$(dirname "$0")/.."
MD=report/report.md
OUT=report/report.pdf

if command -v pandoc >/dev/null 2>&1; then
  pandoc "$MD" -o "$OUT" --pdf-engine=pdflatex \
    -V geometry:margin=2.5cm -V fontsize=11pt
  echo "Wrote $OUT (pandoc)"
  exit 0
fi

if python3 -c "import fpdf" 2>/dev/null; then
  python3 report/build_pdf.py
  exit 0
fi

if command -v npx >/dev/null 2>&1; then
  npx --yes md-to-pdf "$MD" --dest "$OUT"
  echo "Wrote $OUT (md-to-pdf)"
  exit 0
fi

echo "Install pandoc or Node.js, then re-run: bash report/build_pdf.sh"
echo "Or open report/report.md in Word/Google Docs and export as PDF."
exit 1

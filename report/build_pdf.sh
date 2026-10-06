#!/usr/bin/env bash
# Build English + Hebrew report PDFs from markdown.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m pip install -q fpdf2 uharfbuzz
python3 report/build_pdf.py
echo "Open: report/report.pdf  and  report/report.he.pdf"

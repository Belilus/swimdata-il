#!/usr/bin/env python3
"""Build report/report.pdf from report/report.md for Moodle submission."""
from __future__ import annotations
import re
import textwrap
from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parent.parent
MD = ROOT / "report" / "report.md"
OUT = ROOT / "report" / "report.pdf"


def latin1(s: str) -> str:
    return s.encode("latin-1", "replace").decode("latin-1")


class ReportPDF(FPDF):
    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 8, latin1(f"SwimData-IL — page {self.page_no()}"), align="C")


def write_wrapped(pdf: ReportPDF, text: str, *, bold=False, size=10, mono=False):
    font = "Courier" if mono else "Helvetica"
    pdf.set_font(font, "B" if bold else "", size)
    width = pdf.w - pdf.l_margin - pdf.r_margin
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            pdf.ln(2)
            continue
        wrap = 100 if mono else 92
        for line in textwrap.wrap(para, width=wrap, break_long_words=True, replace_whitespace=False):
            pdf.multi_cell(width, 5, latin1(line))
        pdf.ln(1)


def main():
    md = MD.read_text(encoding="utf-8")
    md = re.sub(
        r"```mermaid.*?```",
        "[ER diagram: competition→event→heat→entry→result; swimmer, club, club_name_variant — see docs/schema-design.md]",
        md,
        flags=re.S,
    )

    pdf = ReportPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    in_code = False
    for raw in md.splitlines():
        line = raw.rstrip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if not line.strip():
            pdf.ln(2)
            continue
        if line.startswith("# "):
            write_wrapped(pdf, line[2:], bold=True, size=14)
            pdf.ln(2)
        elif line.startswith("## "):
            write_wrapped(pdf, line[3:], bold=True, size=12)
            pdf.ln(1)
        elif line.startswith("> "):
            write_wrapped(pdf, line[2:], size=9)
        elif line.startswith("|"):
            write_wrapped(pdf, line, size=8, mono=True)
        elif in_code:
            write_wrapped(pdf, line, size=8, mono=True)
        elif line.startswith("- "):
            write_wrapped(pdf, line, size=10)
        else:
            write_wrapped(pdf, line, size=10)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUT))
    print(f"Wrote {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()

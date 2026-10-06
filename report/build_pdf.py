#!/usr/bin/env python3
"""Build readable English and Hebrew PDFs from the report markdown files.

    python3 report/build_pdf.py
    → report/report.pdf      (English)
    → report/report.he.pdf   (Hebrew, RTL)

Needs: pip install fpdf2 uharfbuzz
Uses the system Arial Unicode font so Hebrew and Latin share one typeface.
"""
from __future__ import annotations

import re
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

ROOT = Path(__file__).resolve().parent.parent
# Times New Roman keeps word-spacing under fpdf2; Arial Unicode + shaping
# is required for readable Hebrew (RTL).
FONT_EN = Path("/System/Library/Fonts/Supplemental/Times New Roman.ttf")
FONT_EN_B = Path("/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf")
FONT_HE = Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf")

NAVY = (22, 48, 86)
SLATE = (45, 55, 72)
RULE = (200, 208, 218)
CODE_BG = (245, 247, 250)
HEAD_BG = (22, 48, 86)
ROW_ALT = (246, 248, 251)
QUOTE_BG = (240, 244, 250)


class ReportPDF(FPDF):
    def __init__(self, *, rtl: bool, running: str):
        super().__init__(format="A4")
        self.rtl = rtl
        self.running = running
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(18, 16, 18)
        regular = FONT_HE if rtl else FONT_EN
        bold = FONT_HE if rtl else (FONT_EN_B if FONT_EN_B.exists() else FONT_EN)
        if not regular.exists():
            raise SystemExit(f"Font not found: {regular}")
        self.add_font("Body", "", str(regular))
        self.add_font("Body", "B", str(bold))
        if FONT_EN.exists():
            self.add_font("Code", "", str(FONT_EN))
        else:
            self.add_font("Code", "", str(regular))
        self._apply_shaping()

    def _apply_shaping(self, direction: str | None = None):
        # Shaping on Times New Roman collapses spaces; only use it for Hebrew.
        try:
            if self.rtl or direction == "rtl":
                self.set_text_shaping(True, direction=direction or "rtl")
            elif direction == "ltr":
                self.set_text_shaping(True, direction="ltr")
            else:
                self.set_text_shaping(False)
        except Exception:
            pass

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Body", "", 8)
        self.set_text_color(*SLATE)
        self._apply_shaping()
        self.cell(0, 6, self.running, align="R" if self.rtl else "L")
        self.ln(2)
        self.set_draw_color(*RULE)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-14)
        self.set_draw_color(*RULE)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(2)
        self.set_font("Body", "", 8)
        self.set_text_color(*SLATE)
        self._apply_shaping()
        label = f"{self.page_no()}"
        self.cell(0, 6, label, align="C")

    def _w(self) -> float:
        return self.epw

    def _write(self, text: str, *, size=10.5, bold=False, align=None, color=SLATE, lh=None):
        if not text:
            return
        self.set_font("Body", "B" if bold else "", size)
        self.set_text_color(*color)
        self._apply_shaping()
        if align is None:
            align = "R" if self.rtl else "L"
        self.multi_cell(
            self._w(),
            lh or (size * 0.48 + 1.6),
            text,
            align=align,
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )

    def h1(self, text: str):
        self._write(text, size=16, bold=True, color=NAVY, lh=8)
        self.ln(1)

    def h2(self, text: str):
        self.ln(2)
        self._write(text, size=12.5, bold=True, color=NAVY, lh=7)
        y = self.get_y()
        self.set_draw_color(*NAVY)
        if self.rtl:
            self.line(self.w - self.r_margin - 28, y, self.w - self.r_margin, y)
        else:
            self.line(self.l_margin, y, self.l_margin + 28, y)
        self.ln(3)

    def para(self, text: str):
        self._write(clean_inline(text), size=10.5, color=SLATE, lh=5.4)
        self.ln(1.5)

    def quote(self, text: str):
        x, y = self.l_margin, self.get_y()
        self.set_fill_color(*QUOTE_BG)
        # draw after measuring — write first, then a left/right bar
        self._write(clean_inline(text), size=9.5, color=SLATE, lh=5)
        self.set_draw_color(*NAVY)
        self.set_line_width(0.6)
        if self.rtl:
            self.line(self.w - self.r_margin, y, self.w - self.r_margin, self.get_y())
        else:
            self.line(x, y, x, self.get_y())
        self.set_line_width(0.2)
        self.ln(2)

    def code(self, text: str):
        self.set_fill_color(*CODE_BG)
        self.set_draw_color(*RULE)
        try:
            self.set_text_shaping(False)
        except Exception:
            pass
        self.set_font("Code", "", 8)
        self.set_text_color(*SLATE)
        pad = 2
        start = self.get_y()
        self.set_x(self.l_margin)
        self.multi_cell(
            self._w(),
            4.2,
            text.rstrip() + "\n",
            align="L",
            fill=True,
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        self.rect(self.l_margin, start, self._w(), self.get_y() - start)
        self.ln(2)
        self._apply_shaping()

    def table(self, rows: list[list[str]]):
        if not rows:
            return
        cols = max(len(r) for r in rows)
        rows = [r + [""] * (cols - len(r)) for r in rows]
        usable = self._w()
        # wider first column for bilingual source tables
        if cols == 3:
            widths = [usable * 0.22, usable * 0.22, usable * 0.56]
        else:
            widths = [usable / cols] * cols
        if self.rtl:
            widths = list(reversed(widths))
            rows = [list(reversed(r)) for r in rows]

        self.set_font("Body", "", 8)
        line_h = 4.6
        for i, row in enumerate(rows):
            if self.get_y() > self.h - 28:
                self.add_page()
            # estimate height
            heights = []
            for cell, w in zip(row, widths):
                heights.append(max(line_h, self._cell_h(clean_inline(cell), w, line_h)))
            h = max(heights)
            if i == 0:
                self.set_fill_color(*HEAD_BG)
                self.set_text_color(255, 255, 255)
                bold = True
            else:
                self.set_fill_color(*(ROW_ALT if i % 2 == 0 else (255, 255, 255)))
                self.set_text_color(*SLATE)
                bold = False
            self.set_font("Body", "B" if bold else "", 8)
            self._apply_shaping()
            x = self.l_margin
            y = self.get_y()
            align = "R" if self.rtl else "L"
            for cell, w in zip(row, widths):
                self.set_xy(x, y)
                self.rect(x, y, w, h, style="FD")
                self.set_xy(x + 1.2, y + 0.8)
                self.multi_cell(w - 2.4, line_h, clean_inline(cell), align=align)
                x += w
            self.set_xy(self.l_margin, y + h)
        self.ln(3)

    def _cell_h(self, text: str, width: float, line_h: float) -> float:
        if not text:
            return line_h
        self.set_font("Body", "", 8)
        lines = self.multi_cell(
            width - 2.4, line_h, text, dry_run=True, output="LINES"
        )
        n = max(1, len(lines) if lines else 1)
        return n * line_h + 1.4


def clean_inline(text: str) -> str:
    text = text.replace("**", "").replace("`", "")
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = text.replace("*", "")
    text = text.replace("∈", "in")
    return text.strip()


def parse_blocks(md: str):
    md = re.sub(r"<style[\s\S]*?</style>", "", md)
    md = re.sub(r"</?div[^>]*>", "", md)
    md = re.sub(
        r"```mermaid.*?```",
        "DIAGRAM: competition → event → heat → entry → result ; "
        "swimmer → entry ; club → swimmer ; club → club_name_variant ; "
        "ref_stroke → event",
        md,
        flags=re.S,
    )
    lines = md.splitlines()
    blocks = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            buf = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            blocks.append(("code", "\n".join(buf)))
            i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                raw = lines[i].strip().strip("|")
                cells = [c.strip() for c in raw.split("|")]
                if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            blocks.append(("table", rows))
            continue
        if line.startswith("# "):
            blocks.append(("h1", line[2:].strip()))
            i += 1
            continue
        if line.startswith("## "):
            blocks.append(("h2", line[3:].strip()))
            i += 1
            continue
        if line.startswith("### "):
            blocks.append(("h2", line[4:].strip()))
            i += 1
            continue
        if line.startswith("> "):
            q = []
            while i < len(lines) and lines[i].startswith(">"):
                q.append(lines[i].lstrip("> ").rstrip())
                i += 1
            blocks.append(("quote", " ".join(q)))
            continue
        if line.strip() in {"---", "***"}:
            i += 1
            continue
        if not line.strip():
            i += 1
            continue
        para = [line.strip()]
        i += 1
        while i < len(lines) and lines[i].strip() and not lines[i].startswith(
            ("#", "|", "```", ">", "---")
        ):
            para.append(lines[i].strip())
            i += 1
        text = " ".join(para)
        if text.startswith("DIAGRAM:"):
            blocks.append(("quote", text[8:].strip()))
        else:
            blocks.append(("para", text))
    return blocks


def render(md_path: Path, out_path: Path, *, rtl: bool, running: str):
    md = md_path.read_text(encoding="utf-8")
    pdf = ReportPDF(rtl=rtl, running=running)
    pdf.add_page()
    for kind, payload in parse_blocks(md):
        if kind == "h1":
            pdf.h1(payload)
        elif kind == "h2":
            pdf.h2(payload)
        elif kind == "para":
            pdf.para(payload)
        elif kind == "quote":
            pdf.quote(payload)
        elif kind == "code":
            pdf.code(payload)
        elif kind == "table":
            pdf.table(payload)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out_path))
    print(f"Wrote {out_path}  ({out_path.stat().st_size:,} bytes, {pdf.page_no()} pages)")


def main():
    render(
        ROOT / "report" / "report.md",
        ROOT / "report" / "report.pdf",
        rtl=False,
        running="SwimData-IL  ·  Final project report  ·  Asaf Belilus",
    )
    he = ROOT / "report" / "report.he.md"
    if he.exists():
        render(
            he,
            ROOT / "report" / "report.he.pdf",
            rtl=True,
            running="SwimData-IL  ·  דוח פרויקט גמר  ·  אסף בלילוס",
        )


if __name__ == "__main__":
    main()

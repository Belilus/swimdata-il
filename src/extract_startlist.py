#!/usr/bin/env python3
"""
extract_startlist.py -- ISA "Start list" PDF (Hebrew, RTL) -> tidy CSV

The start list is the *second* source. It is fully Hebrew and right-to-left,
but it carries three things the (English) results PDF does not:

  * club_code   -- a numeric federation club id (language-neutral!)
  * entry_time  -- the swimmer's seed time (or "NT" = no time)
  * the Hebrew spelling of each swimmer + club name

Together with (event-signature, heat, lane) -- which BOTH documents share --
the club_code is the anchor that lets us bridge Hebrew and English identities
deterministically instead of guessing transliterations.

pdfplumber returns each Hebrew token with its glyphs in visual (reversed)
order, so we reverse tokens to recover logical Hebrew. The join keys we rely
on (code, year, lane, heat, distance, age) are numeric and need no reversing;
only stroke/gender keywords are mapped from Hebrew.

Output columns:
  source_file, page, distance_m, stroke, gender, age_group, heat, lane,
  club_code, entry_time_raw, entry_time_ms, birth_year,
  last_name_he, first_name_he, club_he
"""
from __future__ import annotations
import argparse, csv, re, os
import pdfplumber

BANDS = {
    "entry_time":  (40, 100),
    "birth_year":  (110, 155),
    "club_he":     (160, 300),
    "club_code":   (300, 335),
    "last_name":   (355, 430),
    "first_name":  (430, 522),
    "lane":        (535, 575),
}
HE_STROKE = {          # logical Hebrew -> canonical English (match results)
    "חופשי": "Freestyle", "גב": "Backstroke", "חזה": "Breaststroke",
    "פרפר": "Butterfly", "מעורב": "Individual Medley",
}
HE_GENDER = {"בנות": "Girls", "בנים": "Boys", "מעורב": "Mixed"}
TIME_RE = re.compile(r"^(?:(\d+):)?(\d{1,2})\.(\d{2})$")
YOB_RE = re.compile(r"^(19|20)\d{2}$")


def he_logical(tok: str) -> str:
    """Reverse a single visually-ordered Hebrew token to logical order."""
    if any("֐" <= c <= "׿" for c in tok):
        return tok[::-1]
    return tok


def parse_time_ms(raw: str):
    m = TIME_RE.match(raw.strip())
    if not m:
        return None
    mins = int(m.group(1) or 0)
    return ((mins * 60 + int(m.group(2))) * 100 + int(m.group(3))) * 10


def band_of(x0):
    for name, (lo, hi) in BANDS.items():
        if lo <= x0 < hi:
            return name
    return None


def cluster(words, tol=3):
    rows = {}
    for w in words:
        key = next((k for k in rows if abs(k - w["top"]) <= tol), None)
        rows.setdefault(key if key is not None else w["top"], []).append(w)
    return rows


def parse_event_header(text_logical: str):
    """From a logical-Hebrew header line, derive (distance, stroke, gender, age)."""
    nums = re.findall(r"\d+", text_logical)
    stroke = next((HE_STROKE[k] for k in HE_STROKE if k in text_logical), None)
    gender = next((HE_GENDER[k] for k in HE_GENDER if k in text_logical), None)
    if not (stroke and gender and len(nums) >= 3):
        return None
    # header pattern: "משחה <no> - <distance> <stroke> - <gender> <age>"
    ints = [int(n) for n in nums]
    distance = next((n for n in ints if n in
                     (25, 50, 100, 200, 400, 800, 1500)), None)
    age = ints[-1] if ints else None
    if distance is None:
        return None
    return {"distance_m": distance, "stroke": stroke,
            "gender": gender, "age_group": age}


def extract(pdf_path: str):
    out = []
    with pdfplumber.open(pdf_path) as pdf:
        current, heat = None, None
        for pno, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(use_text_flow=False,
                                       keep_blank_chars=False)
            lines = cluster(words, tol=3)
            for top in sorted(lines):
                toks = sorted(lines[top], key=lambda w: -w["x0"])  # RTL order
                logical = " ".join(he_logical(w["text"]) for w in toks)
                # event header?
                if "משחה" in logical:
                    ev = parse_event_header(logical)
                    if ev:
                        current = ev
                        heat = None
                        continue
                # heat header?  "מקצה: N"
                if "מקצה" in logical:
                    m = re.search(r"(\d+)", logical)
                    if m:
                        heat = int(m.group(1))
                    continue

                if current is None or heat is None:
                    continue

                # data row: anchor requires a lane number in the lane band
                lane_ws = [w for w in lines[top]
                           if BANDS["lane"][0] <= w["x0"] < BANDS["lane"][1]
                           and w["text"].isdigit()]
                if not lane_ws:
                    continue
                cells = {}
                for w in lines[top]:
                    b = band_of(w["x0"])
                    if b:
                        cells.setdefault(b, []).append(w)

                def cell(band, logical_he=False):
                    ws = sorted(cells.get(band, []), key=lambda w: -w["x0"])
                    parts = [he_logical(w["text"]) if logical_he else w["text"]
                             for w in ws]
                    return " ".join(parts).strip()

                lane = cell("lane")
                birth_year = cell("birth_year")
                club_code = cell("club_code")
                entry_raw = cell("entry_time")
                # skip if this "row" is actually the column-label line
                if not (birth_year and YOB_RE.match(birth_year)):
                    continue

                out.append({
                    "source_file": os.path.basename(pdf_path),
                    "page": pno,
                    "distance_m": current["distance_m"],
                    "stroke": current["stroke"],
                    "gender": current["gender"],
                    "age_group": current["age_group"],
                    "heat": heat,
                    "lane": lane or None,
                    "club_code": club_code or None,
                    "entry_time_raw": entry_raw or None,
                    "entry_time_ms": parse_time_ms(entry_raw) if entry_raw else None,
                    "birth_year": birth_year or None,
                    "last_name_he": cell("last_name", logical_he=True) or None,
                    "first_name_he": cell("first_name", logical_he=True) or None,
                    "club_he": cell("club_he", logical_he=True) or None,
                })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()
    rows = extract(args.pdf)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    cols = ["source_file", "page", "distance_m", "stroke", "gender",
            "age_group", "heat", "lane", "club_code", "entry_time_raw",
            "entry_time_ms", "birth_year", "last_name_he", "first_name_he",
            "club_he"]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    codes = len({r["club_code"] for r in rows if r["club_code"]})
    seeded = sum(1 for r in rows if r["entry_time_ms"] is not None)
    print(f"[startlist] {len(rows)} entries | {codes} club codes | "
          f"{seeded} seeded ({len(rows)-seeded} NT) -> {args.out}")


if __name__ == "__main__":
    main()

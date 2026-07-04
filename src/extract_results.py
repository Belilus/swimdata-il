#!/usr/bin/env python3
"""
extract_results.py  --  ISA "Results" PDF  ->  tidy CSV (one row per swim)

The Israeli Swimming Association publishes competition results as PDF only
(via loglig.com). The PDF is a fixed-column report, but the text layer is
laced with RTL Hebrew headers, repeated page furniture, and club names that
wrap across 2-3 lines. Naive text extraction (pdftotext) scrambles the
columns, so we parse by *geometry* instead:

  1. Read every word with its (x0, top) coordinates via pdfplumber.
  2. Detect the current event from its header line
     ("400m Freestyle - Girls 11").
  3. Anchor each swimmer on their Year-of-Birth token (every result row has
     exactly one, in a stable x-band) and assign all other words to their
     nearest anchor. This cleanly reunites wrapped club names with their row.
  4. Bucket each anchor's words into columns by x-band and emit one CSV row.

Output columns:
  source_file, page, event_no, distance_m, stroke, gender, age_group,
  rank, heat, lane, last_name, first_name, birth_year, club_raw,
  result_raw, status, time_ms, fina_score

Usage:
  python3 extract_results.py "<results.pdf>" -o ../data/interim/results.csv
"""
from __future__ import annotations
import argparse, csv, re, sys, os
import pdfplumber

# ---- column x-bands (points), derived empirically from the ISA layout -------
BANDS = {
    "rank":       (0,    55),
    "heat":       (55,   90),
    "lane":       (90,   135),
    "last_name":  (135,  200),
    "first_name": (200,  270),
    "birth_year": (270,  305),
    "club":       (305,  435),
    "result":     (435,  500),
    "fina":       (500,  600),
}
LABEL_WORDS = {
    "Rank", "Heat", "Lane", "Last", "First", "name", "Club", "Result",
    "International", "Score", "Year", "Of", "Birth", "Results",
    "Powered", "By",
}
STROKES = ("Freestyle", "Backstroke", "Breaststroke", "Butterfly",
           "Individual Medley", "Medley", "Relay")
EVENT_RE = re.compile(
    r"(\d+)\s*m\s+(.*?)\s*-\s*(Girls|Boys|Mixed)\s+(\d+)", re.IGNORECASE)
YOB_RE = re.compile(r"^(19|20)\d{2}$")
TIME_RE = re.compile(r"^(?:(\d+):)?(\d{1,2})\.(\d{2})$")   # mm:ss.hh or ss.hh
STATUS_TOKENS = {"DNS", "DNF", "DSQ", "NS", "SCR", "WD", "DQ"}


def has_hebrew(s: str) -> bool:
    return any("֐" <= c <= "׿" for c in s)


def band_of(x0: float) -> str | None:
    for name, (lo, hi) in BANDS.items():
        if lo <= x0 < hi:
            return name
    return None


def parse_time_ms(raw: str) -> int | None:
    m = TIME_RE.match(raw.strip())
    if not m:
        return None
    mins = int(m.group(1) or 0)
    secs = int(m.group(2))
    hund = int(m.group(3))
    return ((mins * 60 + secs) * 100 + hund) * 10  # milliseconds


def cluster_rows(words, tol=3):
    """Group words into visual lines by their 'top' coordinate."""
    rows = {}
    for w in words:
        key = None
        for k in rows:
            if abs(k - w["top"]) <= tol:
                key = k
                break
        rows.setdefault(key if key is not None else w["top"], []).append(w)
    return rows


def extract(pdf_path: str):
    out = []
    with pdfplumber.open(pdf_path) as pdf:
        current = None  # (event_no, distance, stroke, gender, age)
        event_no = 0
        last_sig = None  # collapse header reprints on continuation pages
        for pno, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(use_text_flow=False,
                                       keep_blank_chars=False)
            # 1) find event header lines on this page & update context.
            #    A multi-page event reprints its header, so only advance the
            #    event counter when the (distance,stroke,gender,age) signature
            #    actually changes.
            lines = cluster_rows(words, tol=3)
            for top in sorted(lines):
                text = " ".join(w["text"] for w in
                                sorted(lines[top], key=lambda w: w["x0"]))
                m = EVENT_RE.search(text)
                if m and any(s.lower() in text.lower() for s in STROKES):
                    sig = (int(m.group(1)), m.group(2).strip().lower(),
                           m.group(3).lower(), int(m.group(4)))
                    if sig != last_sig:
                        event_no += 1
                        last_sig = sig
                        current = {
                            "event_no": event_no,
                            "distance_m": int(m.group(1)),
                            "stroke": m.group(2).strip(),
                            "gender": m.group(3).capitalize(),
                            "age_group": int(m.group(4)),
                        }
            if current is None:
                continue

            # 2) candidate content words (drop furniture / labels / Hebrew)
            content = [
                w for w in words
                if w["text"] not in LABEL_WORDS
                and not has_hebrew(w["text"])
                and not EVENT_RE.search(w["text"])
                and w["top"] < 790                # above the "Powered By" footer
            ]
            # 3) anchors = Year-of-Birth tokens in the birth_year band
            anchors = [w for w in content
                       if YOB_RE.match(w["text"])
                       and BANDS["birth_year"][0] <= w["x0"] < BANDS["birth_year"][1]]
            if not anchors:
                continue
            anchors.sort(key=lambda w: w["top"])
            anchor_y = [a["top"] for a in anchors]

            # 4) assign every content word to nearest anchor by vertical dist
            buckets = [dict() for _ in anchors]
            for w in content:
                # nearest anchor
                i = min(range(len(anchor_y)),
                        key=lambda j: abs(anchor_y[j] - w["top"]))
                if abs(anchor_y[i] - w["top"]) > 16:   # too far -> not a row word
                    continue
                b = band_of(w["x0"])
                if b:
                    buckets[i].setdefault(b, []).append(w)

            # 5) emit one row per anchor
            for i, bk in enumerate(buckets):
                def cell(band):
                    ws = bk.get(band, [])
                    ws = sorted(ws, key=lambda w: (round(w["top"]), w["x0"]))
                    return " ".join(w["text"] for w in ws).strip()

                def int_str(s):
                    s = (s or "").strip()
                    return s if s.isdigit() else ""

                birth_year = cell("birth_year")
                last_name = cell("last_name")
                first_name = cell("first_name")
                club_raw = re.sub(r"\s+", " ", cell("club"))
                result_raw = cell("result")
                fina = int_str(cell("fina"))
                rank = int_str(cell("rank"))
                heat = int_str(cell("heat"))
                lane = int_str(cell("lane"))

                if not (last_name or first_name):        # skip stray fragments
                    continue

                # classify result: time vs status (normalise DQ->DSQ) and
                # capture the disqualification rule reference (e.g. 'SW 4.4')
                status = None
                dsq_rule = None
                time_ms = parse_time_ms(result_raw)
                if time_ms is None:
                    up = result_raw.upper()
                    mrule = re.search(r"SW\s*[\d.]+", up)
                    dsq_rule = mrule.group(0) if mrule else None
                    if "DNF" in up:
                        status = "DNF"
                    elif "DSQ" in up or "DQ" in up:
                        status = "DSQ"
                    elif "DNS" in up:
                        status = "DNS"
                    elif re.search(r"\bNS\b", up):
                        status = "NS"
                    elif "SCR" in up:
                        status = "SCR"
                    elif "WD" in up:
                        status = "WD"
                    elif up:              # rule-ref only / other marker -> DSQ
                        status = "DSQ"

                out.append({
                    "source_file": os.path.basename(pdf_path),
                    "page": pno,
                    "event_no": current["event_no"],
                    "distance_m": current["distance_m"],
                    "stroke": current["stroke"],
                    "gender": current["gender"],
                    "age_group": current["age_group"],
                    "rank": rank or None,
                    "heat": heat or None,
                    "lane": lane or None,
                    "last_name": last_name,
                    "first_name": first_name,
                    "birth_year": birth_year or None,
                    "club_raw": club_raw or None,
                    "result_raw": result_raw or None,
                    "status": status,
                    "dsq_rule": dsq_rule,
                    "time_ms": time_ms,
                    "fina_score": fina or None,
                })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()

    rows = extract(args.pdf)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    cols = ["source_file", "page", "event_no", "distance_m", "stroke",
            "gender", "age_group", "rank", "heat", "lane", "last_name",
            "first_name", "birth_year", "club_raw", "result_raw", "status",
            "dsq_rule", "time_ms", "fina_score"]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    n = len(rows)
    n_time = sum(1 for r in rows if r["time_ms"] is not None)
    n_status = sum(1 for r in rows if r["status"])
    events = len({r["event_no"] for r in rows})
    print(f"[results] {n} rows | {events} events | "
          f"{n_time} timed | {n_status} status(DNS/DSQ/..) -> {args.out}")


if __name__ == "__main__":
    main()

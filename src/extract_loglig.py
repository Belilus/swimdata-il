#!/usr/bin/env python3
"""
extract_loglig.py -- parser for loglig's Hebrew (RTL) competition-results PDF.

loglig.com (the ISA timing provider) publishes the major-championship results as a
fully Hebrew / right-to-left PDF export, with a single wide table per age-category
holding rank + times + identity + club in one document. This parser reads it by
geometry (like extract_startlist.py):
reverse each Hebrew token to logical order, bucket words into columns by x-band,
and anchor each swimmer on their year-of-birth token.

Individual events only: relay events (distance contains 'X') are flagged and
skipped -- their 4-swimmer team rows have a different shape (future work).

Output columns:
  source_file, page, event_no, distance_m, stroke, gender, age_group,
  position, heat, lane, last_name_he, first_name_he, birth_year, club_he,
  result_raw, status, time_ms, points
"""
from __future__ import annotations
import argparse, csv, re, os
import pdfplumber

# column x-bands for the loglig Hebrew results layout (points ->|<- position)
BANDS = {
    "points":     (16,  95),
    "result":     (95,  175),
    "club":       (175, 300),
    "birth_year": (300, 338),
    "first_name": (338, 400),
    "last_name":  (400, 466),
    "lane":       (466, 500),
    "heat":       (500, 540),
    "position":   (540, 585),
}
HE_STROKE = {"חופשי": "Freestyle", "גב": "Backstroke", "חזה": "Breaststroke",
             "פרפר": "Butterfly", "מעורב": "Individual Medley"}
HE_GENDER = {"בנות": "Girls", "בנים": "Boys", "נשים": "Women",
             "גברים": "Men", "מעורב": "Mixed"}
TIME_RE = re.compile(r"^(?:(\d+):)?(\d{1,2})\.(\d{2})$")
YOB_RE = re.compile(r"^(19|20)\d{2}$")
STATUS = {"NT", "DNS", "DNF", "DQ", "DSQ", "NS", "SCR", "WD"}


def he_logical(t):
    return t[::-1] if any("֐" <= c <= "׿" for c in t) else t


def parse_time_ms(raw):
    m = TIME_RE.match((raw or "").strip())
    if not m:
        return None
    return ((int(m.group(1) or 0) * 60 + int(m.group(2))) * 100 + int(m.group(3))) * 10


def band_of(x0):
    for n, (lo, hi) in BANDS.items():
        if lo <= x0 < hi:
            return n
    return None


def cluster(words, tol=3):
    rows = {}
    for w in words:
        k = next((k for k in rows if abs(k - w["top"]) <= tol), None)
        rows.setdefault(k if k is not None else w["top"], []).append(w)
    return rows


def parse_header(logical):
    """Return event dict from an event header line, else None."""
    stroke = next((HE_STROKE[k] for k in HE_STROKE if k in logical), None)
    nums = re.findall(r"\d+", logical)
    is_relay = bool(re.search(r"\bX\b|X\d|\dX", logical.upper()))
    if not stroke or not nums:
        return None
    dist = next((int(n) for n in nums
                 if int(n) in (25, 50, 100, 200, 400, 800, 1500)), None)
    if dist is None and not is_relay:
        return None
    return {"distance_m": dist, "stroke": stroke, "is_relay": is_relay}


def header_gender(logical):
    """Gender keyword from a header/category line, else None."""
    return next((HE_GENDER[k] for k in HE_GENDER if k in logical), None)


def extract(pdf_path, comp_year):
    out, event_no = [], 0
    cur_event = None
    cur_gender = None
    with pdfplumber.open(pdf_path) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
            lines = cluster(words, tol=3)
            # anchors (birth-year tokens) on this page
            anchors = [w for w in words if YOB_RE.match(w["text"])
                       and BANDS["birth_year"][0] <= w["x0"] < BANDS["birth_year"][1]]
            anchor_tops = sorted(a["top"] for a in anchors)

            for top in sorted(lines):
                toks = sorted(lines[top], key=lambda w: -w["x0"])
                logical = " ".join(he_logical(w["text"]) for w in toks)
                # is this line an anchor row? (has a birth-year token)
                if any(abs(top - at) <= 3 for at in anchor_tops):
                    continue  # handled below via anchor assignment
                h = parse_header(logical)
                if h:
                    cur_event = h
                    g = header_gender(logical)
                    if g:
                        cur_gender = g
                    if not h["is_relay"]:
                        event_no += 1
                    continue
                # standalone gender/category line (e.g. "בנות 14")
                g = header_gender(logical)
                if g and len(logical) < 24:
                    cur_gender = g
                    continue

            if cur_event is None or cur_event.get("is_relay"):
                continue

            # assign every word to nearest birth-year anchor -> one swimmer/row
            buckets = {at: {} for at in anchor_tops}
            for w in words:
                if not anchor_tops:
                    break
                at = min(anchor_tops, key=lambda a: abs(a - w["top"]))
                if abs(at - w["top"]) > 14:
                    continue
                b = band_of(w["x0"])
                if b:
                    buckets[at].setdefault(b, []).append(w)

            for at in anchor_tops:
                bk = buckets[at]

                def cell(band, he=False):
                    ws = sorted(bk.get(band, []), key=lambda w: -w["x0"])
                    return " ".join(he_logical(w["text"]) if he else w["text"]
                                    for w in ws).strip()

                birth_year = cell("birth_year")
                if not YOB_RE.match(birth_year):
                    continue
                # derive age from birth year (robust vs. flaky category headers)
                age_group = comp_year - int(birth_year)
                # normalise Women/Men -> Girls/Boys so gender is female/male
                gender = {"Women": "Girls", "Men": "Boys"}.get(
                    cur_gender or "Mixed", cur_gender or "Mixed")
                result_raw = cell("result")
                pts = re.sub(r"[^0-9]", "", cell("points"))
                time_ms = parse_time_ms(result_raw)
                status = None
                if time_ms is None:
                    up = result_raw.upper()
                    status = next((s for s in STATUS if s in up), "DSQ" if up else None)
                    if status == "DQ":
                        status = "DSQ"
                pos = re.sub(r"[^0-9]", "", cell("position"))
                out.append({
                    "source_file": os.path.basename(pdf_path), "page": pno,
                    "event_no": event_no,
                    "distance_m": cur_event["distance_m"],
                    "stroke": cur_event["stroke"],
                    "gender": gender, "age_group": age_group,
                    "position": pos or None,
                    "heat": re.sub(r"[^0-9]", "", cell("heat")) or None,
                    "lane": re.sub(r"[^0-9]", "", cell("lane")) or None,
                    "last_name_he": cell("last_name", he=True) or None,
                    "first_name_he": cell("first_name", he=True) or None,
                    "birth_year": birth_year,
                    # strip a leaked category label (e.g. "בנות 15 ") off the club
                    "club_he": re.sub(
                        r"^(בנות|בנים|נשים|גברים|מעורב)\s*\d*\s*", "",
                        re.sub(r"\s+", " ", cell("club", he=True))).strip() or None,
                    "result_raw": result_raw or None, "status": status,
                    "time_ms": time_ms, "points": pts or None,
                })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--year", type=int, default=2025,
                    help="competition year, used to derive age from birth year")
    args = ap.parse_args()
    rows = extract(args.pdf, args.year)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    cols = ["source_file", "page", "event_no", "distance_m", "stroke", "gender",
            "age_group", "position", "heat", "lane", "last_name_he",
            "first_name_he", "birth_year", "club_he", "result_raw", "status",
            "time_ms", "points"]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    timed = sum(1 for r in rows if r["time_ms"])
    ev = len({r["event_no"] for r in rows})
    clubs = len({r["club_he"] for r in rows if r["club_he"]})
    print(f"[loglig] {len(rows)} rows | {ev} individual events | {timed} timed | "
          f"{clubs} club spellings -> {args.out}")


if __name__ == "__main__":
    main()

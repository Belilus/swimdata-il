#!/usr/bin/env python3
"""
export_web.py -- query the DuckDB database and emit web/data.js for the
self-contained dashboard (window.SWIM_DATA = {...}). No server needed: the
dashboard reads this file via a <script> tag, so it opens from disk.
"""
from __future__ import annotations
import argparse, json, os
import duckdb

FMT = """CASE WHEN {c} IS NULL THEN NULL ELSE
  lpad(CAST(CAST(FLOOR({c}/60000.0) AS INTEGER) AS VARCHAR),2,'0')||':'||
  lpad(CAST(CAST(FLOOR(({c}%60000)/1000.0) AS INTEGER) AS VARCHAR),2,'0')||'.'||
  lpad(CAST(CAST(FLOOR(({c}%1000)/10.0) AS INTEGER) AS VARCHAR),2,'0') END"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    con = duckdb.connect(args.db, read_only=True)

    def rows(sql):
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    data = {}
    data["meta"] = rows("""
        SELECT (SELECT count(*) FROM result) swims,
               (SELECT count(*) FROM swimmer) swimmers,
               (SELECT count(*) FROM club) clubs,
               (SELECT count(*) FROM event) events,
               (SELECT count(*) FROM competition) competitions,
               (SELECT count(*) FROM club_name_variant) variants""")[0]

    data["competitions"] = rows("""
        SELECT c.competition_id id, c.name_en, c.name_he,
               CAST(c.start_date AS VARCHAR) start_date,
               CAST(c.end_date AS VARCHAR) end_date, c.city, c.course,
               (SELECT count(*) FROM result r JOIN entry en ON en.entry_id=r.entry_id
                 JOIN heat h ON h.heat_id=en.heat_id JOIN event e ON e.event_id=h.event_id
                 WHERE e.competition_id=c.competition_id) swims,
               (SELECT count(DISTINCT en.swimmer_id) FROM entry en JOIN heat h ON h.heat_id=en.heat_id
                 JOIN event e ON e.event_id=h.event_id WHERE e.competition_id=c.competition_id) swimmers,
               (SELECT count(*) FROM event e WHERE e.competition_id=c.competition_id) events
        FROM competition c ORDER BY c.competition_id""")

    # medal table per competition
    data["medals"] = rows(f"""
        SELECT e.competition_id comp, COALESCE(c.name_en,c.name_he) club,
               c.name_he club_he,
               COUNT(*) FILTER (WHERE r.place=1) gold,
               COUNT(*) FILTER (WHERE r.place=2) silver,
               COUNT(*) FILTER (WHERE r.place=3) bronze,
               COUNT(DISTINCT en.swimmer_id) swimmers
        FROM result r JOIN entry en ON en.entry_id=r.entry_id
        JOIN heat h ON h.heat_id=en.heat_id JOIN event e ON e.event_id=h.event_id
        JOIN swimmer sw ON sw.swimmer_id=en.swimmer_id
        JOIN club c ON c.club_id=sw.club_id
        GROUP BY e.competition_id, COALESCE(c.name_en,c.name_he), c.name_he
        HAVING COUNT(*) FILTER (WHERE r.place<=3) > 0
        ORDER BY comp, gold DESC, silver DESC""")

    # events with podium (top 3)
    data["events"] = rows(f"""
        WITH ranked AS (
          SELECT e.event_id, e.competition_id comp, e.distance_m, rs.name_en stroke,
                 e.gender, e.age_group,
                 sw.first_name_en fe, sw.last_name_en le,
                 sw.first_name_he fh, sw.last_name_he lh,
                 COALESCE(c.name_en,c.name_he) club, {FMT.format(c='r.final_time_ms')} t,
                 r.fina_points fina,
                 RANK() OVER (PARTITION BY e.event_id ORDER BY r.final_time_ms) rk
          FROM result r JOIN entry en ON en.entry_id=r.entry_id
          JOIN heat h ON h.heat_id=en.heat_id
          JOIN event e ON e.event_id=h.event_id
          JOIN ref_stroke rs ON rs.stroke_code=e.stroke_code
          JOIN swimmer sw ON sw.swimmer_id=en.swimmer_id
          LEFT JOIN club c ON c.club_id=sw.club_id
          WHERE r.final_time_ms IS NOT NULL)
        SELECT * FROM ranked WHERE rk<=3 ORDER BY comp, distance_m, stroke, gender, age_group, rk""")

    # swimmer directory
    data["swimmers"] = rows("""
        SELECT sw.swimmer_id id, sw.first_name_en fe, sw.last_name_en le,
               sw.first_name_he fh, sw.last_name_he lh, sw.birth_year yob,
               COALESCE(c.name_en,c.name_he) club,
               COUNT(DISTINCT h.event_id) events,
               COUNT(*) FILTER (WHERE r.place<=3) medals,
               MAX(r.fina_points) best_fina
        FROM swimmer sw
        LEFT JOIN club c ON c.club_id=sw.club_id
        LEFT JOIN entry en ON en.swimmer_id=sw.swimmer_id
        LEFT JOIN heat h ON h.heat_id=en.heat_id
        LEFT JOIN result r ON r.entry_id=en.entry_id
        GROUP BY sw.swimmer_id, sw.first_name_en, sw.last_name_en,
                 sw.first_name_he, sw.last_name_he, sw.birth_year, COALESCE(c.name_en,c.name_he)""")

    # per-swimmer swims (for dossiers)
    swims = rows(f"""
        SELECT en.swimmer_id sid, e.competition_id comp, e.distance_m dist, rs.name_en stroke,
               e.age_group age, {FMT.format(c='en.seed_time_ms')} seed,
               CASE WHEN r.final_time_ms IS NULL THEN r.status ELSE {FMT.format(c='r.final_time_ms')} END res,
               r.place, r.fina_points fina
        FROM result r JOIN entry en ON en.entry_id=r.entry_id
        JOIN heat h ON h.heat_id=en.heat_id JOIN event e ON e.event_id=h.event_id
        JOIN ref_stroke rs ON rs.stroke_code=e.stroke_code
        ORDER BY en.swimmer_id, e.distance_m""")
    by_sw = {}
    for s in swims:
        by_sw.setdefault(s.pop("sid"), []).append(s)
    data["swims"] = by_sw

    # entity-resolution showcase: clubs with multiple spellings
    data["club_variants"] = rows("""
        SELECT COALESCE(c.name_en,c.name_he) canonical, c.federation_code code,
               COUNT(*) n, STRING_AGG(v.spelling, ' | ') spellings
        FROM club c JOIN club_name_variant v ON v.club_id=c.club_id
        GROUP BY COALESCE(c.name_en,c.name_he), c.federation_code
        HAVING COUNT(*) > 1 ORDER BY n DESC, canonical""")

    # best swims overall (records board)
    data["records"] = rows(f"""
        SELECT e.competition_id comp, e.distance_m dist, rs.name_en stroke, e.gender, e.age_group age,
               sw.first_name_en fe, sw.last_name_en le, sw.first_name_he fh, sw.last_name_he lh,
               COALESCE(c.name_en,c.name_he) club, {FMT.format(c='r.final_time_ms')} t, r.fina_points fina
        FROM result r JOIN entry en ON en.entry_id=r.entry_id
        JOIN heat h ON h.heat_id=en.heat_id JOIN event e ON e.event_id=h.event_id
        JOIN ref_stroke rs ON rs.stroke_code=e.stroke_code
        JOIN swimmer sw ON sw.swimmer_id=en.swimmer_id
        LEFT JOIN club c ON c.club_id=sw.club_id
        WHERE r.fina_points IS NOT NULL AND r.final_time_ms IS NOT NULL
        ORDER BY r.fina_points DESC LIMIT 24""")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("window.SWIM_DATA = ")
        json.dump(data, f, ensure_ascii=False)
        f.write(";")
    con.close()
    kb = os.path.getsize(args.out) / 1024
    print(f"[web] wrote {args.out} ({kb:.0f} KB) | "
          f"{data['meta']['swims']} swims, {len(data['swimmers'])} swimmers, "
          f"{len(data['events'])} podium rows")


if __name__ == "__main__":
    main()

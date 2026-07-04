#!/usr/bin/env python3
"""
app.py -- a small query application over the ISA swim database.

Per the project spec the emphasis is on DATA MANAGEMENT, not UI, so this is a
deliberately minimal, menu-driven console tool. Every menu item is a
parameterised SQL query against the normalised schema. It runs on the DuckDB
build by default; pointing it at PostgreSQL only means swapping the connect
line for psycopg2 -- the SQL is identical.

    python3 src/app.py                     # interactive menu
    python3 src/app.py standings           # one-shot: club medal table
    python3 src/app.py swimmer MAOZ        # one-shot: search a swimmer
"""
from __future__ import annotations
import os, sys
import duckdb

DB = os.environ.get("ISA_DB",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "build", "isa.duckdb"))

FMT = ("lpad(CAST(CAST(FLOOR({c}/60000.0) AS INTEGER) AS VARCHAR),2,'0')||':'||"
       "lpad(CAST(CAST(FLOOR(({c}%60000)/1000.0) AS INTEGER) AS VARCHAR),2,'0')||'.'||"
       "lpad(CAST(CAST(FLOOR(({c}%1000)/10.0) AS INTEGER) AS VARCHAR),2,'0')")


def connect():
    if not os.path.exists(DB):
        sys.exit(f"database not found at {DB}\n-> run: python3 src/run_pipeline.py")
    return duckdb.connect(DB, read_only=True)


def show(con, sql, params=None):
    import pandas as pd
    df = con.execute(sql, params or []).df()
    if df.empty:
        print("   (no rows)")
    else:
        with pd.option_context('display.max_columns', None, 'display.width', 200,
                               'display.max_colwidth', 30):
            print(df.to_string(index=False))
    print()


def club_standings(con):
    print("\n== Club standings (medal table) ==")
    show(con, """
        SELECT COALESCE(c.name_en,c.name_he) AS club,
               COUNT(*) FILTER (WHERE r.place=1) gold,
               COUNT(*) FILTER (WHERE r.place=2) silver,
               COUNT(*) FILTER (WHERE r.place=3) bronze,
               COUNT(DISTINCT en.swimmer_id) swimmers
        FROM result r JOIN entry en ON en.entry_id=r.entry_id
        JOIN swimmer sw ON sw.swimmer_id=en.swimmer_id
        JOIN club c ON c.club_id=sw.club_id
        GROUP BY 1 ORDER BY gold DESC, silver DESC LIMIT 15""")


def swimmer_search(con, term):
    print(f"\n== Swimmers matching '{term}' ==")
    show(con, """
        SELECT swimmer_id, first_name_en, last_name_en, first_name_he,
               last_name_he, birth_year
        FROM swimmer WHERE UPPER(last_name_en) LIKE '%'||UPPER(?)||'%'
        ORDER BY last_name_en, first_name_en LIMIT 25""", [term])
    print("   -- swims for the first match --")
    show(con, f"""
        SELECT e.distance_m, rs.name_en stroke, e.age_group,
               {FMT.format(c='en.seed_time_ms')} AS seed,
               CASE WHEN r.final_time_ms IS NULL THEN r.status
                    ELSE {FMT.format(c='r.final_time_ms')} END AS result,
               r.place, r.fina_points
        FROM swimmer sw
        JOIN entry en ON en.swimmer_id=sw.swimmer_id
        JOIN heat h ON h.heat_id=en.heat_id
        JOIN event e ON e.event_id=h.event_id
        JOIN ref_stroke rs ON rs.stroke_code=e.stroke_code
        JOIN result r ON r.entry_id=en.entry_id
        WHERE sw.swimmer_id = (
            SELECT swimmer_id FROM swimmer
            WHERE UPPER(last_name_en) LIKE '%'||UPPER(?)||'%'
            ORDER BY last_name_en, first_name_en LIMIT 1)
        ORDER BY e.distance_m""", [term])


def meet_records(con):
    print("\n== Best swims of the meet (by FINA points) ==")
    show(con, f"""
        SELECT e.distance_m, rs.name_en stroke, e.gender, e.age_group,
               sw.first_name_en, sw.last_name_en,
               {FMT.format(c='r.final_time_ms')} AS time, r.fina_points
        FROM result r JOIN entry en ON en.entry_id=r.entry_id
        JOIN heat h ON h.heat_id=en.heat_id
        JOIN event e ON e.event_id=h.event_id
        JOIN ref_stroke rs ON rs.stroke_code=e.stroke_code
        JOIN swimmer sw ON sw.swimmer_id=en.swimmer_id
        WHERE r.final_time_ms IS NOT NULL
        ORDER BY r.fina_points DESC LIMIT 15""")


def club_variants(con):
    print("\n== Entity-resolution report: club name variants ==")
    show(con, """
        SELECT COALESCE(c.name_en,c.name_he) canonical, c.federation_code,
               COUNT(*) variants,
               STRING_AGG(v.spelling,' | ') spellings
        FROM club c JOIN club_name_variant v ON v.club_id=c.club_id
        GROUP BY 1,2 HAVING COUNT(*) > 2 ORDER BY variants DESC LIMIT 15""")


MENU = {"1": ("Club standings", club_standings),
        "2": ("Search a swimmer", None),
        "3": ("Best swims of the meet", meet_records),
        "4": ("Club name-variant report", club_variants)}


def interactive():
    con = connect()
    while True:
        print("\n--- ISA swim database ---")
        for k, (label, _) in MENU.items():
            print(f"  {k}) {label}")
        print("  q) quit")
        choice = input("> ").strip().lower()
        if choice == "q":
            break
        elif choice == "2":
            swimmer_search(con, input("last name contains: ").strip())
        elif choice in MENU:
            MENU[choice][1](con)
        else:
            print("?")
    con.close()


def main():
    if len(sys.argv) == 1:
        interactive(); return
    cmd = sys.argv[1].lower()
    con = connect()
    if cmd == "standings":
        club_standings(con)
    elif cmd == "swimmer" and len(sys.argv) > 2:
        swimmer_search(con, sys.argv[2])
    elif cmd == "records":
        meet_records(con)
    elif cmd == "variants":
        club_variants(con)
    else:
        print("usage: app.py [standings | swimmer <name> | records | variants]")
    con.close()


if __name__ == "__main__":
    main()

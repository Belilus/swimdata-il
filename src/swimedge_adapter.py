#!/usr/bin/env python3
"""
swimedge_adapter.py -- SAFE, ONE-WAY export: course DB -> SwimEdge-shaped bundle.

Maps the course project's normalised tables onto the exact schema/enums of the
SwimEdge product (Club/ClubAlias, Swimmer with Latin+Hebrew names, Event enums,
MeetEntry, Result with source=FEDERATION_INGEST). It only READS the course
DuckDB and WRITES a JSON bundle -- it never touches the SwimEdge codebase or
database. That bundle is exactly the shape SwimEdge's FEDERATION_INGEST path
consumes, so it demonstrates that the two systems' schemas are interoperable.

Output: web/swimedge_bundle.json  + a validation report on stdout.
"""
from __future__ import annotations
import argparse, json, os
import duckdb

STROKE_ENUM = {"Freestyle": "FREESTYLE", "Backstroke": "BACKSTROKE",
               "Breaststroke": "BREASTSTROKE", "Butterfly": "BUTTERFLY",
               "Individual Medley": "MEDLEY"}
GENDER_ENUM = {"Girls": "FEMALE", "Boys": "MALE", "Mixed": "MIXED"}
VALID_DISTANCE = {25, 50, 100, 200, 400, 800, 1500, 3000, 5000}
STATUS_ENUM = {"DNS": "DNS", "DSQ": "DISQUALIFIED", "DNF": "DID_NOT_FINISH",
               "NS": "DNS", "SCR": "SCRATCHED", "WD": "WITHDRAWN"}


def distance_enum(m):
    return f"M_{m}" if m in VALID_DISTANCE else None


def age_group_enum(age):
    if age is None:
        return None
    if 8 <= age <= 16:
        return f"AGE_{age}"
    if age in (17, 18):
        return "AGE_17_18"
    return "SENIOR"


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

    # ---- clubs (+ aliases) → SwimEdge clubs table shape -----------------
    clubs = {}
    for c in rows("SELECT club_id, federation_code, name_en, name_he FROM club"):
        clubs[c["club_id"]] = {
            "federationClubCode": str(c["federation_code"]),
            "name": c["name_en"] or c["name_he"],
            "nameHe": c["name_he"],
            "nameLatin": c["name_en"],
            "aliases": [],
        }
    for v in rows("SELECT club_id, spelling FROM club_name_variant"):
        clubs[v["club_id"]]["aliases"].append(v["spelling"])

    # ---- swimmers → SwimEdge swimmers -----------------------------------
    swimmers = {}
    for s in rows("SELECT swimmer_id, first_name_en, last_name_en, first_name_he,"
                  " last_name_he, birth_year, club_id FROM swimmer"):
        swimmers[s["swimmer_id"]] = {
            "firstName": s["first_name_he"] or s["first_name_en"],
            "lastName": s["last_name_he"] or s["last_name_en"],
            "firstNameLatin": s["first_name_en"],
            "lastNameLatin": s["last_name_en"],
            "birthDate": f"{s['birth_year']}-01-01" if s["birth_year"] else None,
            "federationClubCode": str(
                clubs.get(s["club_id"], {}).get("federationClubCode")) if s["club_id"] else None,
        }

    # ---- competitions / events / entries / results ----------------------
    comps = []
    warn = {"bad_stroke": 0, "bad_distance": 0, "bad_gender": 0}
    for comp in rows("SELECT competition_id, name_he, name_en, "
                     "CAST(start_date AS VARCHAR) s, CAST(end_date AS VARCHAR) e, "
                     "course FROM competition ORDER BY competition_id"):
        cid = comp["competition_id"]
        events = rows(f"""
          SELECT e.event_id, e.distance_m, rs.name_en stroke, e.gender, e.age_group
          FROM event e JOIN ref_stroke rs ON rs.stroke_code=e.stroke_code
          WHERE e.competition_id={cid}""")
        ev_out = []
        for e in events:
            se, de = STROKE_ENUM.get(e["stroke"]), distance_enum(e["distance_m"])
            ge = GENDER_ENUM.get(e["gender"])
            warn["bad_stroke"] += se is None
            warn["bad_distance"] += de is None
            warn["bad_gender"] += ge is None
            results = rows(f"""
              SELECT sw.swimmer_id, en.lane, en.seed_time_ms, r.final_time_ms,
                     r.place, r.status, r.fina_points
              FROM result r JOIN entry en ON en.entry_id=r.entry_id
              JOIN heat h ON h.heat_id=en.heat_id
              JOIN swimmer sw ON sw.swimmer_id=en.swimmer_id
              WHERE h.event_id={e['event_id']}""")
            ev_out.append({
                "stroke": se, "distance": de, "gender": ge,
                "ageGroup": age_group_enum(e["age_group"]),
                "results": [{
                    "swimmerId": r["swimmer_id"],
                    "laneNumber": r["lane"],
                    "entryTimeMillis": r["seed_time_ms"],
                    "swimTimeMillis": r["final_time_ms"],
                    "place": r["place"],
                    "resultStatus": STATUS_ENUM.get(r["status"], "OFFICIAL")
                                    if r["status"] else "OFFICIAL",
                    "finaPoints": r["fina_points"],
                    "source": "FEDERATION_INGEST",
                } for r in results],
            })
        comps.append({
            "nameHe": comp["name_he"], "nameLatin": comp["name_en"],
            "startDate": comp["s"], "endDate": comp["e"],
            "poolType": comp["course"], "events": ev_out,
        })

    bundle = {"source": "swimdata-il/course-project", "version": 1,
              "clubs": list(clubs.values()), "swimmers": swimmers,
              "competitions": comps}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False)

    n_res = sum(len(e["results"]) for c in comps for e in c["events"])
    print(f"[adapter] SwimEdge bundle -> {args.out}")
    print(f"  clubs={len(clubs)}  swimmers={len(swimmers)}  "
          f"competitions={len(comps)}  events={sum(len(c['events']) for c in comps)}  "
          f"results={n_res}")
    print(f"  enum-mapping warnings: {warn}")
    print(f"  every result tagged source=FEDERATION_INGEST; times already in millis")
    con.close()


if __name__ == "__main__":
    main()

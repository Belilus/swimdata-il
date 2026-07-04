#!/usr/bin/env python3
"""
load_loglig.py -- append a loglig (Hebrew) meet into the normalised DB as an
additional competition, resolving club & swimmer identities ACROSS meets.

This is the multi-competition / cross-meet entity-resolution step:
  * clubs   -- matched to existing clubs by normalised Hebrew name; otherwise
               created with a synthetic federation code (>=900000).
  * swimmers-- matched to existing swimmers by (last_he, first_he, birth_year);
               otherwise created. This is how a swimmer seen in the young-ages
               meet and again in the seniors meet becomes ONE row.

Run standalone or via run_pipeline.py --with-loglig.
"""
from __future__ import annotations
import argparse, csv, os, re
import duckdb

STROKE_CODE = {"Freestyle": "FR", "Backstroke": "BK", "Breaststroke": "BR",
               "Butterfly": "FL", "Individual Medley": "IM"}


def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip())


def load(db_path, csv_path, name_he, name_en, start_date, end_date,
         course="LCM", city="Netanya"):
    con = duckdb.connect(db_path)
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
    rows = [r for r in rows if r["birth_year"] and r["last_name_he"]]

    def scalar(q):
        v = con.execute(q).fetchone()[0]
        return v or 0

    # ---- id cursors (continue after existing rows) ----------------------
    ids = {t: scalar(f"SELECT max({t}_id) FROM {t}")
           for t in ["club", "swimmer", "competition", "event", "heat",
                     "entry", "result"]}
    ids["variant"] = scalar("SELECT max(variant_id) FROM club_name_variant")

    def nxt(k):
        ids[k] += 1
        return ids[k]

    # ---- existing lookups for cross-meet matching -----------------------
    club_by_he = {norm(r[1]): r[0] for r in con.execute(
        "SELECT club_id, name_he FROM club WHERE name_he IS NOT NULL").fetchall()}
    max_fed = scalar("SELECT max(federation_code) FROM club")
    syn_code = max(max_fed, 900000)

    swimmer_key = {(norm(r[1]), norm(r[2]), r[3]): r[0] for r in con.execute(
        "SELECT swimmer_id, last_name_he, first_name_he, birth_year "
        "FROM swimmer WHERE last_name_he IS NOT NULL").fetchall()}

    existing_variants = {(r[0], r[1], r[2]) for r in con.execute(
        "SELECT club_id, spelling, lang FROM club_name_variant").fetchall()}

    # ---- competition ----------------------------------------------------
    comp_id = nxt("competition")
    con.execute("INSERT INTO competition (competition_id,name_he,name_en,"
                "start_date,end_date,course,city) VALUES (?,?,?,?,?,?,?)",
                [comp_id, name_he, name_en, start_date, end_date, course, city])

    # ---- resolve clubs --------------------------------------------------
    new_clubs, new_variants = [], []
    club_id_of = {}
    for cname in sorted({norm(r["club_he"]) for r in rows if r["club_he"]}):
        if cname in club_by_he:
            club_id_of[cname] = club_by_he[cname]
        else:
            cid = nxt("club")
            syn_code += 1
            new_clubs.append([cid, syn_code, None, cname])
            club_by_he[cname] = cid
            club_id_of[cname] = cid
        vkey = (club_id_of[cname], cname, "he")
        if vkey not in existing_variants:
            existing_variants.add(vkey)
            new_variants.append([nxt("variant"), club_id_of[cname], cname, "he",
                                 "loglig", 1])
    if new_clubs:
        con.executemany("INSERT INTO club (club_id,federation_code,name_en,name_he)"
                        " VALUES (?,?,?,?)", new_clubs)
    con.executemany("INSERT INTO club_name_variant (variant_id,club_id,spelling,"
                    "lang,source,seen_count) VALUES (?,?,?,?,?,?)", new_variants)

    # ---- resolve swimmers ----------------------------------------------
    def club_for(r):
        return club_id_of.get(norm(r["club_he"])) if r["club_he"] else None

    new_swimmers = []
    swid_of = {}   # per-row swimmer id
    for r in rows:
        k = (norm(r["last_name_he"]), norm(r["first_name_he"]), int(r["birth_year"]))
        if k in swimmer_key:
            swid_of[id(r)] = swimmer_key[k]
        else:
            sid = nxt("swimmer")
            swimmer_key[k] = sid
            swid_of[id(r)] = sid
            new_swimmers.append([sid, None, None, r["last_name_he"],
                                 r["first_name_he"], int(r["birth_year"]),
                                 club_for(r)])
    if new_swimmers:
        con.executemany(
            "INSERT INTO swimmer (swimmer_id,last_name_en,first_name_en,"
            "last_name_he,first_name_he,birth_year,club_id) VALUES (?,?,?,?,?,?,?)",
            new_swimmers)

    # ---- events / heats -------------------------------------------------
    event_id_of, heat_id_of = {}, {}
    ev_rows, heat_rows = [], []
    for r in rows:
        sig = (int(r["distance_m"]), STROKE_CODE.get(r["stroke"]), r["gender"],
               int(r["age_group"]))
        if sig[1] is None:
            continue
        if sig not in event_id_of:
            eid = nxt("event")
            event_id_of[sig] = eid
            ev_rows.append([eid, comp_id, int(r["event_no"] or 0), sig[0], sig[1],
                            sig[2], sig[3], "prelim"])
        hk = (sig, int(r["heat"] or 0))
        if hk not in heat_id_of:
            hid = nxt("heat")
            heat_id_of[hk] = hid
            heat_rows.append([hid, event_id_of[sig], int(r["heat"] or 0)])
    con.executemany("INSERT INTO event (event_id,competition_id,event_no,"
                    "distance_m,stroke_code,gender,age_group,round) "
                    "VALUES (?,?,?,?,?,?,?,?)", ev_rows)
    con.executemany("INSERT INTO heat (heat_id,event_id,heat_no) VALUES (?,?,?)",
                    heat_rows)

    # ---- entries / results (dedupe on heat+lane) ------------------------
    ent_rows, res_rows, seen_lane = [], [], set()
    for r in rows:
        sig = (int(r["distance_m"]), STROKE_CODE.get(r["stroke"]), r["gender"],
               int(r["age_group"]))
        if sig[1] is None:
            continue
        hid = heat_id_of[(sig, int(r["heat"] or 0))]
        lane = int(r["lane"]) if (r["lane"] and r["lane"].isdigit()) else None
        if lane is None or (hid, lane) in seen_lane:
            continue          # a lane hosts one swimmer per heat
        seen_lane.add((hid, lane))
        eid_entry = nxt("entry")
        ent_rows.append([eid_entry, hid, swid_of[id(r)], lane, None])
        time_ms = int(r["time_ms"]) if r["time_ms"] else None
        status = r["status"] or (None if time_ms else "DNS")
        place = int(r["position"]) if (r["position"] and r["position"].isdigit()
                                       and int(r["position"]) > 0) else None
        pts = int(r["points"]) if (r["points"] and r["points"].isdigit()) else None
        res_rows.append([nxt("result"), eid_entry, place, time_ms,
                         None if time_ms else status, None, pts])
    con.executemany("INSERT INTO entry (entry_id,heat_id,swimmer_id,lane,"
                    "seed_time_ms) VALUES (?,?,?,?,?)", ent_rows)
    con.executemany("INSERT INTO result (result_id,entry_id,place,final_time_ms,"
                    "status,dsq_rule,fina_points) VALUES (?,?,?,?,?,?,?)", res_rows)

    print(f"[loglig-load] competition #{comp_id}: +{len(new_clubs)} new clubs, "
          f"+{len(new_swimmers)} new swimmers, {len(ev_rows)} events, "
          f"{len(ent_rows)} swims")
    con.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--name-he", required=True)
    ap.add_argument("--name-en", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    args = ap.parse_args()
    load(args.db, args.csv, args.name_he, args.name_en, args.start, args.end)


if __name__ == "__main__":
    main()

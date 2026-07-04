# Schema design & rationale

Canonical DDL: [`sql/01_schema.sql`](../sql/01_schema.sql). Target DBMS: **PostgreSQL**
(verified end-to-end on DuckDB via `run_pipeline.py`).

## 1. From one wide relation to BCNF

Each source PDF is effectively a single wide relation, e.g. the results sheet is:

```
RESULT_FLAT(event_no, distance, stroke, gender, age, heat, lane,
            last_name, first_name, birth_year, club_name, time, status, fina)
```

This relation is redundant and anomaly-prone: the club name repeats on every swimmer
row (update anomaly — rename a club, touch hundreds of rows), event attributes repeat on
every result row, and you cannot record a heat lane before a time exists (insertion
anomaly). The functional dependencies are:

- `federation_code → club_name_he, club_name_en`
- `event_id → distance, stroke, gender, age_group, round`
- `(event_id, heat_no) → heat`
- `(heat_id, lane) → entry`  and  `entry_id → seed_time`
- `entry_id → result (place, time, status, fina)`
- `swimmer_id → last/first name (he/en), birth_year, club`

Decomposing on these FDs so that **every determinant is a key** gives the BCNF schema
below (8 base tables + 2 staging + 1 lookup). Each fact is stored exactly once.

## 2. Tables

| Table | Grain | Key(s) | Notes |
|-------|-------|--------|-------|
| `ref_stroke` | one stroke | PK `stroke_code` | lookup; FK target for `event` |
| `club` | one club | PK `club_id`, **UNIQUE `federation_code`** | federation code = entity-resolution anchor |
| `club_name_variant` | one observed spelling | PK `variant_id`, UNIQUE `(club_id, spelling, lang)` | dedup audit trail |
| `swimmer` | one person | PK `swimmer_id`, UNIQUE `(last_en, first_en, birth_year, club_id)` | resolved across events |
| `competition` | one meet | PK `competition_id` | dates, course (LCM/SCM), city |
| `event` | one race programme line | PK `event_id`, UNIQUE `(competition, distance, stroke, gender, age, round)` | FK → competition, ref_stroke |
| `heat` | one heat | PK `heat_id`, UNIQUE `(event_id, heat_no)` | FK → event |
| `entry` | seeded lane | PK `entry_id`, UNIQUE `(heat_id, lane)` | FK → heat, swimmer; `seed_time_ms` nullable (`NT`) |
| `result` | swum outcome | PK `result_id`, **UNIQUE `entry_id`** | FK → entry; time XOR status |

## 3. Integrity constraints (and why)

- **Primary keys** on every table; **7 foreign keys** enforce referential integrity
  (no result without an entry, no entry without a heat/swimmer, etc.).
- **`UNIQUE (heat_id, lane)`** — a lane can hold one swimmer per heat.
- **`UNIQUE result.entry_id`** — a swim produces exactly one result (1:1).
- **Domain `CHECK`s** — `distance_m ∈ {25,50,100,200,400,800,1500}`,
  `gender ∈ {Girls,Boys,Mixed}`, `status ∈ {DNS,DSQ,DNF,NS,SCR,WD}`,
  `birth_year ∈ [1990,2020]`, positive times/points.
- **Cross-column `CHECK` (the missing-value rule):**
  `result` requires `final_time_ms IS NOT NULL OR status IS NOT NULL` — a result is
  always either a time or a status, never empty.

## 4. Index choices (workload-driven)

See [`sql/05_indexes_explain.sql`](../sql/05_indexes_explain.sql). Classified on the six
Server1 dimensions:

| Index | Search key | Classification | Serves |
|-------|-----------|----------------|--------|
| `idx_result_time` | `final_time_ms` | secondary, unclustered, dense, single-col, B+-tree | Q1/Q4 ranking, `ORDER BY time LIMIT` |
| `idx_swimmer_name` | `(last,first,birth_year)` | secondary, unclustered, dense, **composite (order matters)**, B+-tree | app swimmer lookup (prefix) |
| `idx_result_fina` | `fina_points` | secondary B+-tree | "best swims of the meet" |
| `idx_entry_swimmer`, `idx_entry_heat`, `idx_heat_event`, `idx_event_lookup` | FK columns | secondary B+-tree | enable index-nested-loop joins (Server4) |

Times are stored as **integer milliseconds** so these indexes are compact and ordering
is exact; human `mm:ss.hh` formatting happens only in the presentation view `v_fmt`.

## 5. Design decisions worth defending in the meeting

1. **Club identity = federation code, not name.** Names are dirty (4 spellings of
   "Maccabi"); the numeric code from the start list is stable and language-neutral.
2. **Split `entry` (seeded) from `result` (swum).** Models "entered but DNS" cleanly and
   keeps seed vs. final as first-class, integrated facts.
3. **Keep a `club_name_variant` audit table.** Entity resolution should be *explainable*
   and reversible, not a black box — you can show exactly which spellings mapped where.
4. **Staging tables are all `TEXT`.** Dirty values (`NT`, `DQ / SW 4.4`, wrapped club
   names) land without failing; cleaning/typing happens in `03_transform.sql`.

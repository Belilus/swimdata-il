# Synchronising the course project with SwimEdge

**Question:** can the course database and parser interoperate with SwimEdge — my
own product — and is that even possible? **Answer: yes, and cleanly**, because
SwimEdge's schema was already designed for exactly this bilingual ISA federation
data. This document is the deep-scan assessment plus the safe, one-way adapter
that proves it.

> **Updated 2026-07-24** to reflect SwimEdge results-ingestion landing (geometry
> results parser + `MeetResultsImportService`). The course repo itself is unchanged.

## 1. What the deep scan found in SwimEdge

SwimEdge (Spring Boot + PostgreSQL, Flyway migrations) models the ISA domain and
ships a full ingestion pipeline:

- **`clubs`**: `name`, `name_he`, `name_latin`, **`federation_club_code`** (unique)
  + **`club_aliases`** — the same "federation code = identity + spelling variants"
  structure as `club` + `club_name_variant` here.
- **`swimmers`**: Hebrew and Latin names + `federation_registration_id`.
- **`results`**: `swim_time_millis`, `result_status`, `fina_points`, and
  **`ResultSource.FEDERATION_INGEST`**.
- **`scripts/ingestion/pdf_meet_parser/`**: geometry parsers for start lists
  (`ISR_GEOMETRY_START_LIST_V1`) and results (`ISR_GEOMETRY_RESULTS_V1`), plus
  regulations parsers. The geometry method was **ported from this project**.
- **`MeetResultsImportService`**: backend service that imports the federation
  results bundle (`source=FEDERATION_INGEST`, idempotent by external ref).

## 2. Schema crosswalk

| Course project | SwimEdge | Mapping |
|----------------|----------|---------|
| `club (federation_code, name_en, name_he)` | `clubs (federation_club_code, name_latin, name_he)` | 1:1 |
| `club_name_variant (spelling)` | `club_aliases (alias_name)` | 1:1 |
| `swimmer (…_en, …_he, birth_year)` | `swimmers (…_latin, …(he), birth_date)` | year → `YYYY-01-01` |
| `competition` | `competitions` | pool/course, dates |
| `event (distance_m, stroke text, gender, age_group)` | `events (Distance, Stroke, Gender, AgeGroup enums)` | value → enum (below) |
| `heat` | `heats` | 1:1 |
| `entry (seed_time_ms)` | `meet_entries (seed_time_millis)` | 1:1 (same units) |
| `result (final_time_ms, status, fina_points)` | `results (swim_time_millis, result_status, …)` | `source=FEDERATION_INGEST` |

**Enum mapping** (validated — 0 warnings over all 340 events):
`Freestyle→FREESTYLE … Individual Medley→MEDLEY`; `50→M_50 … 1500→M_1500`;
`Girls→FEMALE, Boys→MALE, Mixed→MIXED`; `age→AGE_n / AGE_17_18 / SENIOR`;
`DNS/DSQ/DNF→DNS/DISQUALIFIED/DID_NOT_FINISH`.

## 3. The adapter (safe, one-way)

`src/swimedge_adapter.py` **reads** the course DuckDB and **writes**
`web/swimedge_bundle.json` — the shape SwimEdge's import path consumes. It never
touches the SwimEdge codebase or database. Latest run:

```
clubs=72  swimmers=1311  competitions=2  events=340  results=4770
enum-mapping warnings: {bad_stroke:0, bad_distance:0, bad_gender:0}
```

So the course DB → SwimEdge direction is a solved, demonstrable transform.

## 4. Getting the raw data (ingestion capability)

The ISA site (`isr.org.il/Competitions.ASP`) lists each 2025–26 meet and links to
the public loglig results and start-list PDFs. The **Winter 2025 seniors
championship** (147 pages) was obtained this way and parsed into the database as
competition #2. Two format notes learned in practice: young-ages meets export with
Latin names (`extract_results.py` layout); major/seniors meets export fully
**Hebrew/RTL** (`extract_loglig.py`).

## 5. Verdict

Synchronisation is not a stretch — it is the natural conclusion of two systems
built for the same domain. For the course this is the strongest possible framing:
*the database I designed from first principles converges on the schema of a
production system I engineered, and a 60-line adapter maps one to the other with
zero enum mismatches.*

**Post-course (SwimEdge):** the geometry parsers, results canonical model, bundle
format, and `MeetResultsImportService` now close the loop end-to-end in the
product repo. The course project remains the reference implementation for the
data-management story (BCNF, entity resolution, SQL analytics).

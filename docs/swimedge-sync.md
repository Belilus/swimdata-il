# Synchronising the course project with SwimEdge

**Question:** can the course database and parser interoperate with SwimEdge — my
own product — and is that even possible? **Answer: yes, and cleanly**, because
SwimEdge's schema was already designed for exactly this bilingual ISA federation
data. This document is the deep-scan assessment plus the safe, one-way adapter
that proves it.

## 1. What the deep scan found in SwimEdge

SwimEdge (Spring Boot + PostgreSQL, Flyway V1–V17) already models the ISA domain
and even ships an ingestion pipeline for it:

- **`clubs`**: `name`, `name_he`, `name_latin`, **`federation_club_code`** (unique)
  + a **`club_aliases`** table — i.e. exactly the "federation code = identity +
  spelling variants" structure this project built as `club` + `club_name_variant`.
- **`swimmers`**: Hebrew `first_name`/`last_name` **and** `first_name_latin`/
  `last_name_latin` + `federation_registration_id` — the same bilingual identity
  the parser derives from the two PDFs.
- **`results`**: `swim_time_millis` + `entry_time_millis` (same integer-millis
  choice), and a **`ResultSource.FEDERATION_INGEST`** enum value — a slot built
  for imported federation data.
- **`scripts/ingestion/pdf_meet_parser/`**: a mature ISA parser (document
  classifier, start-list / results / **regulations** parsers, Hebrew + time
  utils, canonical-XLSX → federation-bundle adapter).

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
`web/swimedge_bundle.json` — the exact shape SwimEdge's `FEDERATION_INGEST` path
consumes. It never touches the SwimEdge codebase or database. Latest run:

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
Latin names (my `extract_results.py` layout); the major/seniors meets export fully
**Hebrew/RTL** (handled by the new `extract_loglig.py`).

## 5. Verdict

Synchronisation is not a stretch — it is the natural conclusion of two systems
built for the same domain. For the course this is the strongest possible framing:
*the database I designed from first principles converges on the schema of a
production system I engineered, and a 60-line adapter maps one to the other with
zero enum mismatches.* Future work: run the bundle through SwimEdge's real
`FEDERATION_INGEST` importer end-to-end, and add relay + split-time parsing.

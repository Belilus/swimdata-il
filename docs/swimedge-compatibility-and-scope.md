# Project ↔ SwimEdge: table compatibility & scope boundary

Answers two questions the deep read of SwimEdge settled: **do the project's tables
match SwimEdge's?** and **what ships as the course project vs. what is the SwimEdge
combination?**

> **Updated 2026-07-24** after SwimEdge landed geometry results ingestion
> (`IndividualResultRow`, `ISR_GEOMETRY_RESULTS_V1`, `MeetResultsImportService`).
> The course project itself is unchanged and self-contained.

## A. Do the tables match? (DB level — YES)

The course project's normalised tables line up 1:1 with SwimEdge's DB schema. This
is not theory — the `swimedge_adapter.py` already emits SwimEdge-shaped rows with
**0 enum mismatches** across 72 clubs / 1,311 swimmers / 4,770 results.

| Course table | SwimEdge table | Verdict |
|--------------|----------------|---------|
| `club (federation_code, name_en, name_he)` | `clubs (federation_club_code, name_latin, name_he)` | match |
| `club_name_variant` | `club_aliases` | match |
| `swimmer (…_en, …_he, birth_year)` | `swimmers (…_latin, …(he), birth_date)` | match (year→date) |
| `competition` | `competitions` | match |
| `event (distance_m, stroke, gender, age)` | `events (Distance, Stroke, Gender, AgeGroup enums)` | match (value→enum) |
| `heat` | `heats` | match |
| `entry (seed_time_ms)` | `meet_entries (seed_time_millis)` | match |
| `result (final_time_ms, status, fina_points)` | `results (swim_time_millis, result_status, …)` | match |

**Conclusion:** the database schemas are compatible; the project can feed SwimEdge.

## B. Does the ingestion pipeline match? (Contract level — YES, post-SwimEdge work)

When this document was first written, SwimEdge's canonical model was
**entry-shaped only** (`IndividualEntryRow` — seed times, no rank / final time /
FINA / status). That gap is **now closed** in the SwimEdge repo (July 2026):

| Data | SwimEdge canonical model | Status (July 2026) |
|------|--------------------------|--------------------|
| Start list / entry times | `IndividualEntryRow` | `ISR_GEOMETRY_START_LIST_V1` |
| Relay entries | `RelayEntryRow` | exists |
| **Results (place, final time, FINA, status)** | `IndividualResultRow` | `ISR_GEOMETRY_RESULTS_V1` |
| Bundle + backend import | `canonical_to_meet_results_bundle` | `MeetResultsImportService` |

The geometry row-builder in SwimEdge (`geometry_rowbuilder.py`) was **ported from
this project's** `extract_startlist.py` / `extract_results.py` / `extract_loglig.py`.
SwimEdge added completeness gates (`ROW_UNDER_COUNT`), multi-round handling
(`swim_no`, `round`), and the lane-0 header-bleed fix (`row_v_tolerance=7`).

**For the course project:** the parsers here remain the authoritative, self-contained
implementation. SwimEdge is the downstream product — not a dependency for grading.

## C. The scope boundary (what goes where)

### 1. Final course project — ships as-is, self-contained
Everything in **this repository** (`swimdata-il`): the two-source geometry parsers,
BCNF schema, entity resolution, 4,770-swim two-competition database, the dashboard,
the SwimEdge adapter (as a *demonstration* of interoperability), and all docs. It
depends on **nothing** in SwimEdge and is graded on its own. The SwimEdge link is a
bonus narrative, not a dependency.

### 2. SwimEdge combination — done (product repo, not course deliverable)
- Geometry start-list parser + completeness gate (tooling).
- Geometry results parser + `IndividualResultRow` + bundle + backend import service.
- Lives in `newswimedge/scripts/ingestion/pdf_meet_parser/` and
  `com.swimedge.domain.imports.MeetResultsImportService`.

### 3. Not duplicated in the course repo (by design)
End-to-end SwimEdge import (Flyway migrations, Spring services, portal UI) is
product work. The course proves the **data model and transform**; SwimEdge proves
**production ingestion**.

See [`swimedge-sync.md`](swimedge-sync.md) for the schema crosswalk.

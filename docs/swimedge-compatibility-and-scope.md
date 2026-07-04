# Project ↔ SwimEdge: table compatibility & scope boundary

Answers two questions the deep read of SwimEdge settled: **do the project's tables
match SwimEdge's?** and **what ships as the course project vs. what is the SwimEdge
combination?**

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

## B. Does the ingestion pipeline match? (Contract level — PARTIAL)

SwimEdge's offline parser (`scripts/ingestion/pdf_meet_parser/`) converts a PDF to a
canonical model, then to a bundle the backend imports. Its canonical row type is
**entry-shaped** (`IndividualEntryRow` carries `seed_time_millis`) — there is **no
results row type** (no rank / final time / FINA / status). `ISR_TEXT_RESULTS_V1` is
registered but points at the start-list parser (a stub).

| Data | SwimEdge canonical model | Status |
|------|--------------------------|--------|
| Start list / entry times | `IndividualEntryRow` | exists — **compatible** |
| Relay entries | `RelayEntryRow` | exists |
| **Results (place, final time, FINA, status)** | — none — | **GAP** |

So the DB `results` table exists and matches, but the *ingestion path* cannot carry
results yet. Building it is a contract + backend change (see boundary below).

Separately, the existing entry parser is **fragile**: extraction y-buckets words
into lines and the parser reads by token *position*, so a wrapped club name or a
blank cell misaligns columns — exactly the Arena defect. The fix is the geometry
method; it does **not** require any schema change.

## C. The scope boundary (what goes where)

### 1. Final course project — ships as-is, self-contained
Everything in this repository: the two-source geometry parsers,
BCNF schema, entity resolution, 4,770-swim two-competition database, the dashboard,
the SwimEdge adapter (as a *demonstration* of interoperability), and all docs. It
depends on **nothing** in SwimEdge and is graded on its own. The SwimEdge link is a
bonus narrative, not a dependency.

### 2. SwimEdge combination — in-bounds now (tooling only, no schema/backend)
Port the proven geometry method into SwimEdge's parser for the **existing** entry
contract: a word-level extractor + geometry row-builder + a completeness gate, with
golden-fixture tests. This fixes the merged-rows / misaligned-columns bug for start
lists / entry times without touching the schema, the backend, or the bundle format.

### 3. Future — larger change, out of scope here (crosses into backend/contract)
End-to-end **results ingestion** so a platform could archive *past competitions*: a
new `IndividualResultRow` canonical model + results sheet + bundle section + a backend
results-import service writing to the existing `results` table. It spans tooling
**and** backend and is a fundamental change → **out of scope for this course project.**

See [`swimedge-sync.md`](swimedge-sync.md) for the schema crosswalk.

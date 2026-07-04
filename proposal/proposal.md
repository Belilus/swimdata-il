# Project proposal — SwimData-IL

**Student:** Asaf Belilus · **Course:** Data Management, BGU Spring 2026

## Topic
A relational database over **Israeli Swimming Association (ISA)** competition results,
which are published publicly but **only as PDF** (via `isr.org.il` → `loglig.com`).

## Real-world data (spec req. 1)
Public ISA competition PDFs — for each meet: an English **results** sheet, a Hebrew
**start list**, and the **regulations**. One meet ≈ 1,700 swims / 74 events / ~500
swimmers / ~39 clubs; the archive spans dozens of meets per year, so the data scales.

## Data-management challenge (spec req. 2)
**Multi-source bilingual entity resolution.** Integrate the English results and Hebrew
(RTL) start list into single swimmer/club identities, de-duplicate inconsistent club
spellings (4 spellings of "Maccabi"), and handle missing/special values (`NT` seed
times, `DNS/DQ/DNF`). Bridge = shared `(event, heat, lane)` + numeric federation club
code.

## Database design (req. 3)
Normalised (BCNF) schema: `competition, event, heat, entry, result, swimmer, club,
club_name_variant, ref_stroke` with PKs, FKs, `UNIQUE`/`CHECK` constraints, and a
"time XOR status" rule. Federation code is the club identity anchor.

## Implementation (req. 4–5)
PostgreSQL schema + a Python `pdfplumber` extractor + SQL transformation performing the
integration and resolution. Meaningful SQL: window functions (podium ranking, personal
bests), `GROUP BY/HAVING`, set operators, conditional aggregation, plus an
index/`EXPLAIN` study tied to the Server lectures.

## Application (req. 6)
A minimal console app (`app.py`) running parameterised queries — standings, swimmer
lookup, meet records, entity-resolution report. Emphasis on data, not UI.

## Deliverables
Report (`report/report.md`), this repository, and an evaluation-meeting demo. A full
run is one command: `python3 src/run_pipeline.py`.

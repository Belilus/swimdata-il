# 2-minute guided walkthrough (for the evaluation)

A fast path through the project for the reviewer.

## 1. Build & open the dashboard (one command)
The swimmer-level dataset and dashboard are generated locally (not committed — see
*Data & privacy* in the README). Place the meet PDFs in `samples/` and run:

```bash
python3 -m pip install -r requirements.txt
bash build.sh          # → web/dashboard.html
```

Open **`web/dashboard.html`**. Then:
- **Overview** — two real championships, 4,770 swims, the KPI cards.
- **Medal Table** — switch competitions; conditional-aggregation SQL behind it.
- **Events & Podiums** — filter by stroke/gender; each podium is a `RANK()` window
  function that excludes DSQ/DNS (three-valued logic).
- **Swimmers** — search a name (English *or* Hebrew) → click a row for a bilingual
  dossier with seed-vs-final times.
- **Data Challenge** — the live entity-resolution panel: raw club spellings
  collapsing to canonical clubs.

## 2. The report (the graded artifact)
Read **`report/report.md`** (≤5 pages): application overview, data sources, the
data-management challenge, database design, and representative SQL.

## 3. What the build produced (verification)
`bash build.sh` parses the meet PDFs in `samples/`, builds the normalised DB, prints the
verification (row counts + **0 orphan foreign keys**), and regenerates the exports and
dashboard.

## 4. Talking points the reviewer may probe
| Question | Where |
|---|---|
| "Why is this BCNF?" | `docs/schema-design.md` (FDs + decomposition) |
| "Show meaningful SQL." | `sql/04_queries.sql` (window fns, GROUP BY/HAVING, INTERSECT) |
| "What's the data-management challenge?" | `report/report.md` §3 + the dashboard panel |
| "How do indexes help?" | `sql/05_indexes_explain.sql` (EXPLAIN) |
| "How did you handle dirty/missing data?" | NT→NULL, DQ→DSQ, casing, the `DNF`-leak self-heal — `docs/schema-design.md` |
| "Every course topic?" | `docs/course-concept-map.md` |

## 5. Real-world hook
`docs/swimedge-sync.md` shows the same schema mapping onto a production swimming
platform (the author's) with **zero enum mismatches** — the course prototype feeding a
real system.

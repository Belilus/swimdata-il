# SwimData-IL

**Turning the Israeli Swimming Association's PDF-only competition results into a
normalised relational database — with real entity resolution, meaningful SQL, and
an interactive dashboard.**

> Final project — **Data Management, Ben-Gurion University (Spring 2026)**, Yuval
> Moskovitch. Student: **Asaf Belilus**.  
> **Repository:** https://github.com/Belilus/swimdata-il · [`SUBMISSION.md`](SUBMISSION.md)

---

## See it in one command
Run `bash build.sh` (deps: `pip install -r requirements.txt`) to build **`web/dashboard.html`**
from the source PDFs, then open it in any browser — a single self-contained file:
medal tables, event podiums, searchable bilingual swimmer dossiers, a records board,
and a live "data challenge" panel, all from the real data below. The generated
dataset and dashboard are **not committed** — see [Data & privacy](#data--privacy).

## What it is
The ISA publishes competition results **only as PDF** (via `loglig.com`). This
project parses those PDFs by *geometry* (word coordinates → column bands, not fragile
text order), normalises them to **BCNF**, resolves messy bilingual identities, and
loads a database you can query. It contains **two real championships**:

|  | Meet 1 (young-ages, 2 sources) | Meet 2 (winter seniors, loglig) | Total |
|--|--|--|--|
| swims | 1,701 | 3,069 | **4,770** |
| swimmers | 496 | 815 | **1,311** |
| clubs | 39 | +33 | **72** |
| events | 74 | 266 | **340** |

**0 orphan foreign keys.** Full write-up: **[`report/report.md`](report/report.md)**
(≤5 pages, the graded deliverable).

## The data-management challenge (the headline)
**Bilingual entity resolution.** The same club is spelled four ways (*Macabbi /
Maccabi / Maccabbi / Macabi*), in two languages and scripts, across two sources and
two meets. Keying on the numeric **federation code** and picking the canonical name by
statistical mode collapses **72 spellings → 39 clubs**, with an auditable trail — and
a Hebrew start list is bridged to an English results sheet via the shared
`(event, heat, lane)` tuple at **98.3%** deterministic match. See the live panel in
the dashboard and `docs/schema-design.md`.

## Reproduce it (one command)
```bash
python3 -m pip install -r requirements.txt
bash build.sh                # parse both meets → normalised DB → dashboard + exports
python3 src/app.py           # optional: interactive console query app
```
Canonical SQL targets **PostgreSQL** (`sql/01_schema.sql`); the runner executes the
identical SQL on an embedded **DuckDB** so it reproduces with zero server setup.

## Where to look
```
report/report.md            the ≤5-page report  ← start here
SUBMISSION.md               submission guide + repo link for the evaluator
web/index.html              the dashboard UI (data.js + dashboard.html are generated)
DEMO.md                     2-minute guided walkthrough for the evaluation
docs/
  schema-design.md          ER, functional dependencies, BCNF rationale, indexes
  course-concept-map.md     every course topic → where it's demonstrated
  pipeline.md               the ETL flow
sql/
  01_schema.sql             PostgreSQL DDL (keys, constraints, indexes)
  03_transform.sql          staging → core: integration + entity resolution
  04_queries.sql            representative analytical queries (tagged by concept)
  05_indexes_explain.sql    index rationale + EXPLAIN
src/                        geometry PDF parsers, loaders, exporter, query app
samples/                    source-format sample (regulations PDF; meet PDFs not committed)
```

## Data source & scope
Public ISA results (`isr.org.il/Competitions.ASP` → `loglig.com`). This repository is
**self-contained**. It also documents how the same model integrates with a production
swimming platform the author is building (`docs/swimedge-sync.md`) — a real-world
application, described at the design level only.

## Data & privacy
The competition data is published publicly by the ISA, but it identifies individual
swimmers — **including minors**. To avoid redistributing personal data, the raw meet
PDFs and every generated swimmer-level artifact are **kept out of version control**:

- **not committed:** `web/data.js`, `web/dashboard.html`, `web/swimedge_bundle.json`,
  `docs/sample-query-output.txt`, `data/`, and the meet PDFs in `samples/`
  (`results_*`, `startlist_*`);
- **committed:** all code, the PostgreSQL schema and SQL, the report and design docs,
  and a single **regulations** sample PDF (rules only, no personal data).

Everything regenerates locally: place the public meet PDFs in `samples/` and run
`./build.sh` to rebuild the database, exports, and dashboard.

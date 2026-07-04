# Pipeline (ETL) — how the data flows and how to run it

```
 ISA PDFs                 extract (geometry)        load             transform (SQL)
┌──────────────┐  pdfplumber  ┌────────────┐  read_csv  ┌───────────┐  02/03  ┌──────────────┐
│ Results (EN) │ ───────────▶ │ results.csv│ ─────────▶ │ stg_*     │ ──────▶ │ normalised   │
│ Start list(HE)│ ───────────▶ │startlist.csv│          │ (all TEXT)│         │ core (BCNF)  │
└──────────────┘              └────────────┘            └───────────┘         └──────────────┘
                                                                                     │ verify
                                                                                     ▼
                                                                          app.py / 04_queries.sql
```

## Stages

1. **Extract** (`src/extract_results.py`, `src/extract_startlist.py`)
   Coordinate-based parsing. Reads each word's `(x, y)`, recovers fixed column bands,
   anchors each swimmer on their year-of-birth (results) / lane (start list), and
   reunites wrapped club names. Emits tidy CSVs to `data/interim/`.

2. **Load staging** (`run_pipeline.py`)
   CSVs land verbatim in `stg_results` / `stg_startlist` (all columns `TEXT`) so no
   dirty value can break the load.

3. **Transform** (`sql/03_transform.sql`) — the "T" and the data-management story:
   - build a **swim bridge** = results `LEFT JOIN` start list on
     `(distance, stroke, gender, age, heat, lane)`;
   - resolve **clubs** by federation code, canonical name by modal spelling;
   - resolve **swimmers** across events; attach modal club + Hebrew name;
   - populate `competition → event → heat → entry → result`;
   - clean missing/special values (`NT`→NULL, `DQ`→`DSQ`, capture `SW x.y`).

4. **Verify** (`run_pipeline.py` §5): row counts + **zero orphan FK** assertions.

## Run it

```bash
cd "Data management/work/project"
python3 -m pip install pdfplumber duckdb pandas   # once
python3 src/run_pipeline.py                        # extract → load → transform → verify
python3 src/app.py                                 # interactive query app
python3 src/app.py standings                       # or one-shot commands
```

To run against **PostgreSQL** instead of the embedded DuckDB: create a database, run
`psql -f sql/01_schema.sql`, `\copy` the two CSVs into the staging tables, then
`psql -f sql/03_transform.sql`. The SQL is identical; only IDENTITY autoincrement is
PostgreSQL-native (the DuckDB runner strips it and supplies ids explicitly).

## Expected output (one sample championship)

`stg_* = 1701` · `club = 39` · `club_name_variant = 72` · `swimmer = 496` ·
`event = 74` · `heat = 203` · `entry = 1701` · `result = 1701` · orphan FKs `= 0`.

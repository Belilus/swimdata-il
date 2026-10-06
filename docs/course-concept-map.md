# Course-concept map — where every topic shows up in the project

**Hebrew:** [`course-concept-map.he.md`](course-concept-map.he.md)

This is the "I learned the course" cheat-sheet for the evaluation meeting. For each
unit taught this semester (per `study/LESSON_INDEX.md`), it points to the exact place
in the project that demonstrates it. Bring this to the demo.

| Course unit | Concept | Where it's demonstrated |
|-------------|---------|--------------------------|
| **01-intro** | raw data → cleaning → structured DB → queries; what a DBMS gives you over a flat file | The whole pipeline: PDF (flat) → `stg_*` → normalised core. Talking point: the PDF *is* the "random pile"; the schema is the "organised library". |
| **SQL1** | SELECT-FROM-WHERE, inner joins, `AS`, set ops (`UNION`/`INTERSECT`/`EXCEPT`) | `sql/04_queries.sql` Q1–Q10; **Q9 uses `INTERSECT`** (versatile swimmers). The 5-table star join in `v_swim`. |
| **SQL2** | `NULL` semantics & three-valued logic; `WHERE` pitfalls | **Q6** (DNS breakdown) treats a `NULL` time as *unknown*, not 0; seed `NT` stays `NULL`. Table `CHECK` "time XOR status". `COUNT(col)` vs `COUNT(*)` to count non-nulls. |
| **SQL3** | `COUNT/SUM`, `GROUP BY`, `HAVING`, evaluation order | **Q3** club standings (conditional aggregation), **Q5** `HAVING ≥ 10 swimmers`, **Q8** `GROUP BY dsq_rule`, **Q10** `HAVING`. |
| **Server1** | I/O model, buffer, heap vs sorted files, **index classification (6 dims)**, B+-tree | `docs/schema-design.md` §indexes classifies each index; `result(final_time_ms)` = secondary, unclustered, dense B+-tree. `05_indexes_explain.sql` §1. |
| **Server2** | B+-tree search/insert/split; composite keys, prefix use, order matters | Composite `idx_swimmer_name(last, first, birth_year)` — usable for name-prefix lookups; discussed in `05_indexes_explain.sql`. |
| **Server3** | SQL → relational algebra; selection cost table-scan vs index; `B(R),T(R),V(R,a)` | `05_indexes_explain.sql` Q2/Q3 (`EXPLAIN` an indexed selection); report §5 frames podium query as σ/π/⋈. |
| **Server4** | Join algorithms: NL, **BNL**, **INL**, sort-merge, hash | `05_indexes_explain.sql` Q4: the `result→entry→heat→event→swimmer` join; FK indexes let the optimiser choose **INL over BNL**. |
| **Server5** | Optimizer: logical→physical plan, **selection pushdown**, plan cost | `EXPLAIN ANALYZE` before/after `DROP INDEX`; pushing `final_time_ms IS NOT NULL` before the join. |
| **Normalization** (midterm) | FDs, keys, lossless decomposition, **BCNF/3NF** | `docs/schema-design.md` lists the FDs and shows the BCNF decomposition of the one wide PDF relation into 8 tables. |
| **Data cleaning** (`DataCleaning.pdf`) | dedup, missing values, integration, standardisation | The entire §3 challenge: club canonicalisation by mode, `NT`/DSQ missing values, two-source integration, name-casing normalisation. |

## Data-management challenge (the required "non-trivial" one)

Multi-source **bilingual entity resolution**: reconcile a Hebrew (RTL) start list and an
English results sheet into single swimmer/club identities via a shared
`(event, heat, lane)` bridge + numeric federation code — 98.3 % deterministic 1:1 match,
72 club spellings → 39 clubs, with an auditable variant table and self-healing of a
leaked-status data defect.

## Likely evaluation-meeting questions — and the answer to point at

- *"Why is this in BCNF?"* → `docs/schema-design.md` (FD list + decomposition).
- *"Show meaningful SQL, not `SELECT *`."* → Q1 (window), Q3 (agg), Q9 (`INTERSECT`).
- *"What's your data-management challenge?"* → §3 above; run `app.py variants`.
- *"How do indexes help here?"* → `EXPLAIN` in `05`, tie to Server1–5.
- *"How did you handle missing/dirty data?"* → `NT`, DSQ normalisation, `COALESCE` for
  the 6 English-less clubs, the `DNF`-leak self-heal, and the 29 unmatched bridge rows.
- *"What about the 1.7% that did not match? Why LEFT JOIN, not RIGHT?"* → **Those 29
  rows are kept.** The bridge is a `LEFT JOIN` from results to the start list
  (`sql/03_transform.sql`). Results are the fact: an official swim exists. The start
  list only enriches (club code, Hebrew, seed time). The 29 have no deterministic
  match (scratch / lane change) so `club_code`, Hebrew name and seed stay `NULL` —
  no fuzzy name matching. **RIGHT JOIN is not used:** it would keep start-list-only
  people with no results row. The load grain is a result row, and every `swim` row
  creates both `entry` and `result`. Stay with `LEFT JOIN`.

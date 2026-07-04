-- =====================================================================
--  05_indexes_explain.sql  --  indexing + query-plan showcase
--  Ties the project to the SERVER lectures (I/O model, B+-tree indexes,
--  selection cost, join algorithms, optimizer). Written for PostgreSQL;
--  run each EXPLAIN with and without the index to see the plan change.
--  (DuckDB prints a different plan shape but honours the same EXPLAIN.)
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. WHY these indexes exist (mapping workload -> access path)
-- ---------------------------------------------------------------------
--  idx_result_time  (result.final_time_ms)
--      Q1/Q4 rank swims by time inside each event. A B+-tree on
--      final_time_ms turns "find the fastest" into a range/orderscan
--      instead of a full heap scan + sort  (Server1: sorted access;
--      Server3: selection via index ~2-4 I/O for a tree probe).
--
--  idx_swimmer_name (last_name_en, first_name_en, birth_year)
--      The application looks swimmers up by name. A COMPOSITE B+-tree is
--      usable for (last), (last,first) and (last,first,birth_year) prefixes
--      -- "order matters" (Server1, dimension 5 of index classification).
--
--  idx_entry_swimmer / idx_entry_heat / idx_heat_event
--      These are the FOREIGN-KEY join columns. Indexing them lets the
--      optimiser choose INDEX-NESTED-LOOP over BLOCK-NESTED-LOOP for the
--      result->entry->heat->event->swimmer star join (Server4: INL beats
--      BNL when the inner side has a selective index).

-- ---------------------------------------------------------------------
-- 2. Selection by an indexed key -- expect an Index Scan, not Seq Scan
-- ---------------------------------------------------------------------
EXPLAIN
SELECT * FROM swimmer
WHERE last_name_en = 'MAOZ' AND first_name_en = 'ADI';

-- ---------------------------------------------------------------------
-- 3. Range / ordering on an indexed measure -- top of the B+-tree scan
-- ---------------------------------------------------------------------
EXPLAIN
SELECT entry_id, final_time_ms
FROM result
WHERE final_time_ms IS NOT NULL
ORDER BY final_time_ms
LIMIT 10;

-- ---------------------------------------------------------------------
-- 4. The star join behind the podium query -- watch the join operators
-- ---------------------------------------------------------------------
EXPLAIN
SELECT e.distance_m, rs.name_en, sw.last_name_en, r.final_time_ms
FROM result r
JOIN entry   en ON en.entry_id = r.entry_id
JOIN heat    h  ON h.heat_id  = en.heat_id
JOIN event   e  ON e.event_id = h.event_id
JOIN ref_stroke rs ON rs.stroke_code = e.stroke_code
JOIN swimmer sw ON sw.swimmer_id = en.swimmer_id
WHERE r.final_time_ms IS NOT NULL;

-- ---------------------------------------------------------------------
-- 5. Demonstrate the difference an index makes (PostgreSQL):
--       DROP INDEX idx_result_time;      -- force a Seq Scan + Sort
--       EXPLAIN ANALYZE <query 3>;       -- note the cost / actual time
--       CREATE INDEX idx_result_time ON result(final_time_ms);
--       EXPLAIN ANALYZE <query 3>;       -- Index Scan, lower cost
-- ---------------------------------------------------------------------

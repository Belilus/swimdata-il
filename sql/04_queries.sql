-- =====================================================================
--  04_queries.sql  --  representative analytical queries
--  Each block is tagged with the COURSE CONCEPT it demonstrates.
--  Runs on PostgreSQL and DuckDB. A helper view formats milliseconds back
--  into mm:ss.hh for readability.
-- =====================================================================

CREATE OR REPLACE VIEW v_swim AS
SELECT e.event_id, e.distance_m, rs.name_en AS stroke, e.gender, e.age_group,
       h.heat_no, en.lane, sw.swimmer_id,
       sw.first_name_en, sw.last_name_en, sw.first_name_he, sw.last_name_he,
       sw.birth_year, c.club_id,
       COALESCE(c.name_en, c.name_he) AS club,     -- 6 clubs have no English
       c.name_en AS club_en, c.name_he AS club_he, -- name in the source -> fall
       en.seed_time_ms, r.place, r.final_time_ms,   -- back to Hebrew for display
       r.status, r.dsq_rule, r.fina_points
FROM result r
JOIN entry   en ON en.entry_id = r.entry_id
JOIN heat    h  ON h.heat_id  = en.heat_id
JOIN event   e  ON e.event_id = h.event_id
JOIN ref_stroke rs ON rs.stroke_code = e.stroke_code
JOIN swimmer sw ON sw.swimmer_id = en.swimmer_id
LEFT JOIN club c ON c.club_id = sw.club_id;

-- format helper (mm:ss.hh) -- integer-safe on both PostgreSQL and DuckDB.
-- Uses integer modulo (%) for remainders and FLOOR(.. / N.0) for the
-- divisions, so no float rounding can corrupt the components.
CREATE OR REPLACE VIEW v_fmt AS
SELECT *,
   CASE WHEN final_time_ms IS NULL THEN status ELSE
     lpad(CAST(CAST(FLOOR(final_time_ms/60000.0) AS INTEGER) AS VARCHAR),2,'0') || ':' ||
     lpad(CAST(CAST(FLOOR((final_time_ms%60000)/1000.0) AS INTEGER) AS VARCHAR),2,'0') || '.' ||
     lpad(CAST(CAST(FLOOR((final_time_ms%1000)/10.0) AS INTEGER) AS VARCHAR),2,'0')
   END AS final_time,
   CASE WHEN seed_time_ms IS NULL THEN NULL ELSE
     lpad(CAST(CAST(FLOOR(seed_time_ms/60000.0) AS INTEGER) AS VARCHAR),2,'0') || ':' ||
     lpad(CAST(CAST(FLOOR((seed_time_ms%60000)/1000.0) AS INTEGER) AS VARCHAR),2,'0') || '.' ||
     lpad(CAST(CAST(FLOOR((seed_time_ms%1000)/10.0) AS INTEGER) AS VARCHAR),2,'0')
   END AS seed_time
FROM v_swim;


-- Q1 -- WINDOW FUNCTION (RANK) : official podium (top-3) of every event,
--       ranking ONLY valid swims (a DSQ/DNS must not take a medal).
--       Concept: window functions, PARTITION BY, filtering NULLs.
SELECT distance_m, stroke, gender, age_group,
       podium, first_name_en, last_name_en, club, final_time
FROM (
  SELECT f.*,
         RANK() OVER (PARTITION BY event_id ORDER BY final_time_ms) AS podium
  FROM v_fmt f
  WHERE final_time_ms IS NOT NULL          -- exclude DSQ/DNS/DNF (the 3VL rule)
) t
WHERE podium <= 3
ORDER BY distance_m, stroke, gender, age_group, podium;


-- Q2 -- SEED vs FINAL improvement : who dropped the most time.
--       Concept: arithmetic on integrated columns + NULL handling
--       (swimmers who entered 'NT' have no seed -> excluded, not treated 0).
SELECT first_name_en, last_name_en, club_en, distance_m, stroke, age_group,
       seed_time, final_time,
       ROUND((seed_time_ms - final_time_ms)/1000.0, 2) AS improved_sec
FROM v_fmt
WHERE seed_time_ms IS NOT NULL AND final_time_ms IS NOT NULL
ORDER BY (seed_time_ms - final_time_ms) DESC
LIMIT 15;


-- Q3 -- CLUB STANDINGS : medals + total FINA points per club.
--       Concept: multi-table JOIN, conditional aggregation, GROUP BY, ORDER BY.
SELECT COALESCE(c.name_en, c.name_he) AS club,
       COUNT(*) FILTER (WHERE r.place = 1) AS gold,
       COUNT(*) FILTER (WHERE r.place = 2) AS silver,
       COUNT(*) FILTER (WHERE r.place = 3) AS bronze,
       COUNT(DISTINCT en.swimmer_id)        AS swimmers,
       SUM(COALESCE(r.fina_points,0))        AS fina_points
FROM result r
JOIN entry en ON en.entry_id = r.entry_id
JOIN swimmer sw ON sw.swimmer_id = en.swimmer_id
JOIN club c ON c.club_id = sw.club_id
GROUP BY COALESCE(c.name_en, c.name_he)
ORDER BY gold DESC, fina_points DESC
LIMIT 12;


-- Q4 -- AGE-GROUP RECORDS : the single fastest swim per event of the meet.
--       Concept: DISTINCT ON / window top-1, correlated ranking.
SELECT distance_m, stroke, gender, age_group, first_name_en, last_name_en,
       club, final_time, fina_points
FROM (
  SELECT f.*, ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY final_time_ms) rn
  FROM v_fmt f WHERE final_time_ms IS NOT NULL
) t
WHERE rn = 1
ORDER BY fina_points DESC
LIMIT 15;


-- Q5 -- GROUP BY + HAVING : clubs that brought a real squad (>= 10 swimmers).
--       Concept: aggregation with a HAVING filter (post-aggregate predicate).
SELECT COALESCE(c.name_en, c.name_he) AS club, COUNT(DISTINCT sw.swimmer_id) AS swimmers
FROM swimmer sw JOIN club c ON c.club_id = sw.club_id
GROUP BY COALESCE(c.name_en, c.name_he)
HAVING COUNT(DISTINCT sw.swimmer_id) >= 10
ORDER BY swimmers DESC;


-- Q6 -- NULL / THREE-VALUED LOGIC : did-not-start breakdown.
--       Concept: NULL semantics -- a NULL time is NOT 0; a swimmer with a
--       seed time who then did not start is a genuine 'entered but absent'.
SELECT status,
       COUNT(*)                                  AS n,
       COUNT(seed_time_ms)                       AS had_seed_time,
       COUNT(*) - COUNT(seed_time_ms)            AS entered_NT
FROM v_swim
WHERE final_time_ms IS NULL          -- i.e. status IS NOT NULL
GROUP BY status
ORDER BY n DESC;


-- Q7 -- ENTITY-RESOLUTION AUDIT : the clubs whose names were messiest.
--       Concept: the data-management challenge, made queryable.
SELECT c.name_en AS canonical_en, c.federation_code,
       COUNT(*) FILTER (WHERE v.lang='en') AS en_spellings,
       COUNT(*) FILTER (WHERE v.lang='he') AS he_spellings,
       STRING_AGG(CASE WHEN v.lang='en' THEN v.spelling END, ' | ') AS english_variants
FROM club c JOIN club_name_variant v ON v.club_id = c.club_id
GROUP BY c.name_en, c.federation_code
HAVING COUNT(*) FILTER (WHERE v.lang='en') >= 1
ORDER BY en_spellings DESC, canonical_en
LIMIT 12;


-- Q8 -- DISQUALIFICATION ANALYSIS : most common DQ rule references.
--       Concept: GROUP BY on a cleaned/derived column.
SELECT dsq_rule, COUNT(*) AS disqualifications
FROM result
WHERE status = 'DSQ' AND dsq_rule IS NOT NULL
GROUP BY dsq_rule
ORDER BY disqualifications DESC;


-- Q9 -- SET OPERATION : versatile swimmers -- swam freestyle AND butterfly.
--       Concept: INTERSECT (course set operators).
SELECT first_name_en, last_name_en FROM v_swim WHERE stroke='Freestyle'
INTERSECT
SELECT first_name_en, last_name_en FROM v_swim WHERE stroke='Butterfly'
ORDER BY last_name_en
LIMIT 15;


-- Q10 -- BUSIEST SWIMMERS : most events entered (multi-event athletes).
--        Concept: COUNT DISTINCT, GROUP BY, HAVING, ORDER BY, JOIN.
SELECT sw.first_name_en, sw.last_name_en, sw.birth_year,
       COALESCE(c.name_en, c.name_he) AS club,
       COUNT(DISTINCT h.event_id) AS events_entered,
       COUNT(*) FILTER (WHERE r.place <= 3) AS medals
FROM result r
JOIN entry en ON en.entry_id=r.entry_id
JOIN heat h ON h.heat_id=en.heat_id
JOIN swimmer sw ON sw.swimmer_id=en.swimmer_id
LEFT JOIN club c ON c.club_id=sw.club_id
GROUP BY sw.swimmer_id, sw.first_name_en, sw.last_name_en, sw.birth_year, COALESCE(c.name_en, c.name_he)
HAVING COUNT(DISTINCT h.event_id) >= 4
ORDER BY medals DESC, events_entered DESC
LIMIT 15;

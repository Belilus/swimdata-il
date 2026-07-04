-- =====================================================================
--  03_transform.sql  --  staging  ->  normalised core (ELT "T" step)
--  Runs on PostgreSQL and DuckDB. This file IS the data-management story:
--  it integrates the two sources, resolves club & swimmer identities, and
--  handles missing / special values -- all in declarative SQL.
-- =====================================================================

-- ---------- reference + competition seed --------------------------------
INSERT INTO ref_stroke (stroke_code, name_en, name_he) VALUES
    ('FR','Freestyle','חופשי'),
    ('BK','Backstroke','גב'),
    ('BR','Breaststroke','חזה'),
    ('FL','Butterfly','פרפר'),
    ('IM','Individual Medley','מעורב אישי');

INSERT INTO competition (competition_id, name_he, name_en, start_date, end_date, course, city)
VALUES (1,
    'מוקדמות אליפות "ארנה" ישראל קיץ 2026 לגילאים צעירים - דרום',
    'Arena Israel Summer 2026 Youth Championship (South) - Prelims',
    DATE '2026-06-19', DATE '2026-06-27', 'LCM', 'Netanya');

-- ---------- swim bridge: integrate the two sources ----------------------
--  LEFT JOIN so results with no matching start-list entry (scratches /
--  lane changes) survive with a NULL club_code = an honest missing value.
CREATE TEMP TABLE swim AS
SELECT
    CAST(NULLIF(TRIM(r.event_no),'')   AS INTEGER)        AS event_no,
    CAST(NULLIF(TRIM(r.distance_m),'') AS INTEGER)        AS distance_m,
    r.stroke                                              AS stroke_en,
    r.gender                                              AS gender,
    CAST(NULLIF(TRIM(r.age_group),'')  AS INTEGER)        AS age_group,
    CAST(NULLIF(TRIM(r.heat),'')       AS INTEGER)        AS heat_no,
    CAST(NULLIF(TRIM(r.lane),'')       AS INTEGER)        AS lane,
    UPPER(TRIM(r.last_name))                              AS last_en,
    UPPER(TRIM(r.first_name))                             AS first_en,
    CAST(NULLIF(TRIM(r.birth_year),'') AS INTEGER)        AS birth_year,
    -- strip a status token that leaked into the club cell (e.g. '... DNF')
    NULLIF(regexp_replace(TRIM(r.club_raw),
           '\s+(DNF|DNS|DSQ|NS|SCR|WD)$',''), '')         AS club_en_raw,
    NULLIF(CAST(NULLIF(TRIM(r.rank),'') AS INTEGER), 0)   AS place,
    CAST(NULLIF(TRIM(r.time_ms),'')    AS INTEGER)        AS final_time_ms,
    NULLIF(r.status,'')                                   AS status,
    NULLIF(TRIM(r.dsq_rule),'')                           AS dsq_rule,
    CAST(NULLIF(TRIM(r.fina_score),'') AS INTEGER)        AS fina_points,
    CAST(NULLIF(TRIM(s.club_code),'')  AS INTEGER)        AS club_code,
    CAST(NULLIF(TRIM(s.entry_time_ms),'') AS INTEGER)     AS seed_ms,
    s.last_name_he, s.first_name_he, s.club_he
FROM stg_results r
LEFT JOIN stg_startlist s
       ON  CAST(NULLIF(TRIM(r.distance_m),'') AS INTEGER) = CAST(NULLIF(TRIM(s.distance_m),'') AS INTEGER)
       AND r.stroke = s.stroke AND r.gender = s.gender
       AND CAST(NULLIF(TRIM(r.age_group),'') AS INTEGER)  = CAST(NULLIF(TRIM(s.age_group),'') AS INTEGER)
       AND CAST(NULLIF(TRIM(r.heat),'') AS INTEGER)       = CAST(NULLIF(TRIM(s.heat),'') AS INTEGER)
       AND CAST(NULLIF(TRIM(r.lane),'') AS INTEGER)       = CAST(NULLIF(TRIM(s.lane),'') AS INTEGER);

-- ---------- CLUB resolution: federation_code is the identity ------------
--  canonical name = the most frequently observed spelling (statistical
--  mode via a window rank). This auto-heals casing + spelling variants and
--  demotes the 1-off corrupted spelling.
INSERT INTO club (club_id, federation_code, name_en, name_he)
WITH en AS (
    SELECT club_code, club_en_raw AS nm, COUNT(*) c
    FROM swim WHERE club_code IS NOT NULL AND club_en_raw IS NOT NULL
    GROUP BY club_code, club_en_raw),
en_pick AS (
    SELECT club_code, nm,
           ROW_NUMBER() OVER (PARTITION BY club_code ORDER BY c DESC, nm) rn
    FROM en),
he AS (
    SELECT club_code, club_he AS nm, COUNT(*) c
    FROM swim WHERE club_code IS NOT NULL AND club_he IS NOT NULL
    GROUP BY club_code, club_he),
he_pick AS (
    SELECT club_code, nm,
           ROW_NUMBER() OVER (PARTITION BY club_code ORDER BY c DESC, nm) rn
    FROM he),
codes AS (SELECT DISTINCT club_code FROM swim WHERE club_code IS NOT NULL)
SELECT ROW_NUMBER() OVER (ORDER BY codes.club_code),
       codes.club_code,
       e.nm, h.nm
FROM codes
LEFT JOIN en_pick e ON e.club_code = codes.club_code AND e.rn = 1
LEFT JOIN he_pick h ON h.club_code = codes.club_code AND h.rn = 1;

-- ---------- CLUB name variants: the entity-resolution audit trail -------
INSERT INTO club_name_variant (variant_id, club_id, spelling, lang, source, seen_count)
SELECT ROW_NUMBER() OVER (ORDER BY club_id, lang, spelling), club_id, spelling, lang, source, seen_count
FROM (
    SELECT c.club_id, v.club_en_raw AS spelling, 'en' AS lang,
           'results' AS source, COUNT(*) AS seen_count
    FROM swim v JOIN club c ON c.federation_code = v.club_code
    WHERE v.club_en_raw IS NOT NULL
    GROUP BY c.club_id, v.club_en_raw
    UNION ALL
    SELECT c.club_id, v.club_he, 'he', 'startlist', COUNT(*)
    FROM swim v JOIN club c ON c.federation_code = v.club_code
    WHERE v.club_he IS NOT NULL
    GROUP BY c.club_id, v.club_he
) t;

-- ---------- SWIMMER resolution: collapse ~1700 swims -> distinct people --
--  identity = (last_en, first_en, birth_year); modal club + Hebrew name
--  attached. UPPER/TRIM already applied in `swim`, healing casing variants.
INSERT INTO swimmer (swimmer_id, last_name_en, first_name_en, last_name_he, first_name_he, birth_year, club_id)
WITH people AS (
    SELECT last_en, first_en, birth_year FROM swim
    WHERE last_en IS NOT NULL
    GROUP BY last_en, first_en, birth_year),
club_pick AS (   -- modal non-null club per person
    SELECT last_en, first_en, birth_year, club_code,
           ROW_NUMBER() OVER (PARTITION BY last_en, first_en, birth_year
                              ORDER BY COUNT(*) DESC) rn
    FROM swim WHERE club_code IS NOT NULL
    GROUP BY last_en, first_en, birth_year, club_code),
he_pick AS (     -- modal Hebrew name per person
    SELECT last_en, first_en, birth_year, last_name_he, first_name_he,
           ROW_NUMBER() OVER (PARTITION BY last_en, first_en, birth_year
                              ORDER BY COUNT(*) DESC) rn
    FROM swim WHERE last_name_he IS NOT NULL
    GROUP BY last_en, first_en, birth_year, last_name_he, first_name_he)
SELECT ROW_NUMBER() OVER (ORDER BY p.last_en, p.first_en, p.birth_year),
       p.last_en, p.first_en, h.last_name_he, h.first_name_he, p.birth_year, c.club_id
FROM people p
LEFT JOIN club_pick cp ON cp.last_en=p.last_en AND cp.first_en=p.first_en
       AND cp.birth_year=p.birth_year AND cp.rn=1
LEFT JOIN club cl2 ON cl2.federation_code = cp.club_code
LEFT JOIN club c ON c.club_id = cl2.club_id
LEFT JOIN he_pick h ON h.last_en=p.last_en AND h.first_en=p.first_en
       AND h.birth_year=p.birth_year AND h.rn=1;

-- ---------- EVENT / HEAT structure --------------------------------------
INSERT INTO event (event_id, competition_id, event_no, distance_m, stroke_code, gender, age_group, round)
SELECT ROW_NUMBER() OVER (ORDER BY MIN(s.event_no)), 1, MIN(s.event_no),
       s.distance_m, rs.stroke_code, s.gender, s.age_group, 'prelim'
FROM swim s JOIN ref_stroke rs ON rs.name_en = s.stroke_en
GROUP BY s.distance_m, rs.stroke_code, s.gender, s.age_group;

INSERT INTO heat (heat_id, event_id, heat_no)
SELECT ROW_NUMBER() OVER (ORDER BY e.event_id, h.heat_no), e.event_id, h.heat_no
FROM (SELECT DISTINCT distance_m, stroke_en, gender, age_group, heat_no FROM swim WHERE heat_no IS NOT NULL) h
JOIN ref_stroke rs ON rs.name_en = h.stroke_en
JOIN event e ON e.distance_m=h.distance_m AND e.stroke_code=rs.stroke_code
            AND e.gender=h.gender AND e.age_group=h.age_group;

-- ---------- ENTRY (seeded) ----------------------------------------------
INSERT INTO entry (entry_id, heat_id, swimmer_id, lane, seed_time_ms)
SELECT ROW_NUMBER() OVER (ORDER BY hh.heat_id, s.lane), hh.heat_id, sw.swimmer_id, s.lane,
       MIN(s.seed_ms)
FROM swim s
JOIN ref_stroke rs ON rs.name_en = s.stroke_en
JOIN event e ON e.distance_m=s.distance_m AND e.stroke_code=rs.stroke_code
            AND e.gender=s.gender AND e.age_group=s.age_group
JOIN heat hh ON hh.event_id=e.event_id AND hh.heat_no=s.heat_no
JOIN swimmer sw ON sw.last_name_en=s.last_en AND sw.first_name_en=s.first_en
              AND sw.birth_year=s.birth_year
WHERE s.lane IS NOT NULL
GROUP BY hh.heat_id, sw.swimmer_id, s.lane;

-- ---------- RESULT (swum) -----------------------------------------------
--  one row per entry; carries a time OR a status (never neither).
INSERT INTO result (result_id, entry_id, place, final_time_ms, status, dsq_rule, fina_points)
SELECT ROW_NUMBER() OVER (ORDER BY en.entry_id), en.entry_id,
       s.place,
       s.final_time_ms,
       CASE WHEN s.final_time_ms IS NULL
            THEN COALESCE(s.status, 'DNS') END,          -- default missing -> DNS
       s.dsq_rule,
       s.fina_points
FROM swim s
JOIN ref_stroke rs ON rs.name_en = s.stroke_en
JOIN event e ON e.distance_m=s.distance_m AND e.stroke_code=rs.stroke_code
            AND e.gender=s.gender AND e.age_group=s.age_group
JOIN heat hh ON hh.event_id=e.event_id AND hh.heat_no=s.heat_no
JOIN swimmer sw ON sw.last_name_en=s.last_en AND sw.first_name_en=s.first_en
              AND sw.birth_year=s.birth_year
JOIN entry en ON en.heat_id=hh.heat_id AND en.lane=s.lane;

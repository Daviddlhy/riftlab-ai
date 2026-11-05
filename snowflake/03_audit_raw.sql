-- A1 / A2 : audit des sources RAW, avant toute transformation.
-- Exécuter section par section dans Snowsight et conserver les résultats.
-- Aucune donnée ni aucun objet persistant n'est modifié.
-- Les effectifs sont ceux de Snowflake au moment de l'exécution, pas un nombre attendu figé.

USE ROLE SYSADMIN;
USE WAREHOUSE RIFTLAB_WH;
USE DATABASE RIFTLAB_DEV;
USE SCHEMA RAW;

-- 1. Contexte et structure : colonnes attendues PAYLOAD, SOURCE_FILE, LOADED_AT.
SELECT
    CURRENT_TIMESTAMP() AS audited_at,
    CURRENT_ROLE() AS active_role,
    CURRENT_WAREHOUSE() AS active_warehouse,
    CURRENT_DATABASE() AS active_database,
    CURRENT_SCHEMA() AS active_schema;

DESCRIBE TABLE RAW.MATCHES;
DESCRIBE TABLE RAW.TIMELINES;

-- 2. Volumes et complétude. Les compteurs d'anomalies doivent valoir zéro.
-- NULLIF/TRIM détectent aussi un identifiant vide ; le cast traite le JSON null en SQL NULL.
WITH raw_sources AS (
    SELECT 'MATCHES' AS source_table, payload, source_file, loaded_at
    FROM RAW.MATCHES
    UNION ALL
    SELECT 'TIMELINES', payload, source_file, loaded_at
    FROM RAW.TIMELINES
), normalized AS (
    SELECT *, NULLIF(TRIM(payload:metadata:matchId::STRING), '') AS match_id
    FROM raw_sources
), expected_sources AS (
    SELECT column1 AS source_table FROM VALUES ('MATCHES'), ('TIMELINES')
), summary AS (
    SELECT
        source_table,
        COUNT(*) AS row_count,
        COUNT(DISTINCT match_id) AS distinct_match_ids,
        COALESCE(COUNT_IF(match_id IS NULL), 0) AS missing_match_ids,
        COUNT(match_id) - COUNT(DISTINCT match_id) AS duplicate_extra_rows,
        COALESCE(COUNT_IF(COALESCE(TYPEOF(payload), 'SQL_NULL') <> 'OBJECT'), 0)
            AS invalid_payloads,
        COALESCE(COUNT_IF(NULLIF(TRIM(source_file), '') IS NULL), 0) AS missing_source_files,
        COALESCE(COUNT_IF(loaded_at IS NULL), 0) AS missing_loaded_at,
        MIN(loaded_at) AS first_loaded_at,
        MAX(loaded_at) AS last_loaded_at
    FROM normalized
    GROUP BY source_table
)
SELECT
    e.source_table,
    COALESCE(s.row_count, 0) AS row_count,
    COALESCE(s.distinct_match_ids, 0) AS distinct_match_ids,
    COALESCE(s.missing_match_ids, 0) AS missing_match_ids,
    COALESCE(s.duplicate_extra_rows, 0) AS duplicate_extra_rows,
    COALESCE(s.invalid_payloads, 0) AS invalid_payloads,
    COALESCE(s.missing_source_files, 0) AS missing_source_files,
    COALESCE(s.missing_loaded_at, 0) AS missing_loaded_at,
    s.first_loaded_at,
    s.last_loaded_at
FROM expected_sources e
LEFT JOIN summary s ON e.source_table = s.source_table
ORDER BY e.source_table;

-- 3. Détail des IDs absents. Résultat attendu : aucune ligne.
WITH raw_sources AS (
    SELECT 'MATCHES' AS source_table, payload, source_file, loaded_at
    FROM RAW.MATCHES
    UNION ALL
    SELECT 'TIMELINES', payload, source_file, loaded_at
    FROM RAW.TIMELINES
)
SELECT source_table, source_file, loaded_at, TYPEOF(payload) AS payload_type
FROM raw_sources
WHERE NULLIF(TRIM(payload:metadata:matchId::STRING), '') IS NULL
ORDER BY source_table, source_file;

-- 4. Doublons : aucune ligne attendue. Ne pas supprimer automatiquement.
-- Les signatures JSON servent au diagnostic ; elles ne prouvent pas une différence métier
-- (notamment si seule la représentation des objets diffère).
WITH raw_sources AS (
    SELECT 'MATCHES' AS source_table, payload, source_file, loaded_at
    FROM RAW.MATCHES
    UNION ALL
    SELECT 'TIMELINES', payload, source_file, loaded_at
    FROM RAW.TIMELINES
), normalized AS (
    SELECT *, NULLIF(TRIM(payload:metadata:matchId::STRING), '') AS match_id
    FROM raw_sources
)
SELECT
    source_table,
    match_id,
    COUNT(*) AS row_count,
    COUNT(DISTINCT source_file) AS distinct_source_files,
    COUNT(DISTINCT SHA2(TO_JSON(payload), 256)) AS distinct_json_signatures,
    MIN(loaded_at) AS first_loaded_at,
    MAX(loaded_at) AS last_loaded_at
FROM normalized
WHERE match_id IS NOT NULL
GROUP BY source_table, match_id
HAVING COUNT(*) > 1
ORDER BY source_table, match_id;

-- 5. Couverture des paires. L'agrégation préalable évite de multiplier les doublons.
WITH matches AS (
    SELECT NULLIF(TRIM(payload:metadata:matchId::STRING), '') AS match_id, COUNT(*) AS copies
    FROM RAW.MATCHES
    WHERE NULLIF(TRIM(payload:metadata:matchId::STRING), '') IS NOT NULL
    GROUP BY 1
), timelines AS (
    SELECT NULLIF(TRIM(payload:metadata:matchId::STRING), '') AS match_id, COUNT(*) AS copies
    FROM RAW.TIMELINES
    WHERE NULLIF(TRIM(payload:metadata:matchId::STRING), '') IS NOT NULL
    GROUP BY 1
), pairs AS (
    SELECT
        COALESCE(m.match_id, t.match_id) AS match_id,
        m.copies AS match_copies,
        t.copies AS timeline_copies,
        CASE
            WHEN m.match_id IS NULL THEN 'TIMELINE_WITHOUT_MATCH'
            WHEN t.match_id IS NULL THEN 'MATCH_WITHOUT_TIMELINE'
            ELSE 'COMPLETE_PAIR'
        END AS pair_status
    FROM matches m
    FULL OUTER JOIN timelines t ON m.match_id = t.match_id
)
SELECT pair_status, COUNT(*) AS match_ids
FROM pairs
GROUP BY pair_status
ORDER BY pair_status;

-- 6. Liste des orphelins. Résultat attendu : aucune ligne, sinon expliquer la couverture.
WITH matches AS (
    SELECT DISTINCT NULLIF(TRIM(payload:metadata:matchId::STRING), '') AS match_id
    FROM RAW.MATCHES
), timelines AS (
    SELECT DISTINCT NULLIF(TRIM(payload:metadata:matchId::STRING), '') AS match_id
    FROM RAW.TIMELINES
)
SELECT
    COALESCE(m.match_id, t.match_id) AS match_id,
    IFF(m.match_id IS NULL, 'TIMELINE_WITHOUT_MATCH', 'MATCH_WITHOUT_TIMELINE') AS issue
FROM matches m
FULL OUTER JOIN timelines t ON m.match_id = t.match_id
WHERE (m.match_id IS NULL OR t.match_id IS NULL)
    AND COALESCE(m.match_id, t.match_id) IS NOT NULL
ORDER BY match_id;

-- 7. Forme des tableaux. NULL signale un tableau absent, JSON null ou de mauvais type.
WITH structures AS (
    SELECT
        'MATCHES' AS source_table,
        NULLIF(TRIM(payload:metadata:matchId::STRING), '') AS match_id,
        source_file,
        ARRAY_SIZE(payload:info:participants) AS participant_count,
        ARRAY_SIZE(payload:info:teams) AS team_count,
        NULL::INTEGER AS frame_count
    FROM RAW.MATCHES
    UNION ALL
    SELECT
        'TIMELINES',
        NULLIF(TRIM(payload:metadata:matchId::STRING), ''),
        source_file,
        ARRAY_SIZE(payload:info:participants),
        NULL::INTEGER,
        ARRAY_SIZE(payload:info:frames)
    FROM RAW.TIMELINES
)
SELECT *
FROM structures
WHERE COALESCE(participant_count, 0) = 0
    OR (source_table = 'MATCHES' AND COALESCE(team_count, 0) = 0)
    OR (source_table = 'TIMELINES' AND COALESCE(frame_count, 0) = 0)
ORDER BY source_table, match_id;

-- Suite : exécuter 04_profile_kpi_inputs.sql après résolution/qualification des anomalies.

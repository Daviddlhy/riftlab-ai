-- A3 : exploration des champs nécessaires aux KPI, sans créer de modèles persistants.
-- À lancer après 03_audit_raw.sql. Les résultats comptent les lignes RAW :
-- des doublons non résolus peuvent donc gonfler les effectifs.
-- Aucun filtre de queue/carte ni exclusion de partie n'est appliqué implicitement.

USE ROLE SYSADMIN;
USE WAREHOUSE RIFTLAB_WH;
USE DATABASE RIFTLAB;
USE SCHEMA RAW;

-- 1. Périmètre réellement disponible. Confirmer queue, carte et patch avant les KPI.
SELECT
    TRY_TO_NUMBER(payload:info:queueId::STRING) AS queue_id,
    TRY_TO_NUMBER(payload:info:mapId::STRING) AS map_id,
    payload:info:gameMode::STRING AS game_mode,
    payload:info:gameVersion::STRING AS game_version,
    ARRAY_SIZE(payload:info:participants) AS participant_count,
    ARRAY_SIZE(payload:info:teams) AS team_count,
    COUNT(*) AS raw_rows
FROM RIFTLAB.RAW.MATCHES
GROUP BY 1, 2, 3, 4, 5, 6
ORDER BY raw_rows DESC, game_version;

-- 2. Contrôle des unités de durée. Les timestamps sources sont supposés en ms,
-- gameDuration en secondes : comparer les deux mesures avant de valider l'hypothèse.
-- Le delta est diagnostique (fin de jeu et durée peuvent différer légèrement).
WITH durations AS (
    SELECT
        payload:metadata:matchId::STRING AS match_id,
        source_file,
        TRY_TO_NUMBER(payload:info:gameStartTimestamp::STRING) AS start_ms,
        TRY_TO_NUMBER(payload:info:gameEndTimestamp::STRING) AS end_ms,
        TRY_TO_NUMBER(payload:info:gameDuration::STRING) AS duration_value
    FROM RIFTLAB.RAW.MATCHES
)
SELECT
    match_id,
    source_file,
    TO_TIMESTAMP_NTZ(start_ms, 3) AS game_start_utc,
    duration_value AS duration_assuming_seconds,
    ROUND(duration_value / 60.0, 2) AS duration_assuming_minutes,
    (end_ms - start_ms) / 1000.0 AS elapsed_seconds_from_timestamps,
    duration_value - (end_ms - start_ms) / 1000.0 AS duration_delta_seconds,
    CASE
        WHEN duration_value IS NULL OR duration_value <= 0 THEN 'INVALID_DURATION'
        WHEN start_ms IS NULL OR end_ms IS NULL THEN 'MISSING_TIMESTAMPS'
        WHEN end_ms <= start_ms THEN 'INVALID_TIMESTAMP_ORDER'
        ELSE 'COMPARE_UNITS'
    END AS review_status
FROM durations
ORDER BY match_id;

-- 3. Qualité des champs de fin de partie : absence ≠ zéro.
-- Une valeur négative est invalide ; zéro est légitime pour plusieurs statistiques.
-- OUTER garde une ligne diagnostique pour les matchs sans participant exploitable.
WITH participants AS (
    SELECT
        p.value AS participant,
        NULLIF(TRIM(p.value:puuid::STRING), '') AS puuid,
        TRY_TO_NUMBER(p.value:participantId::STRING) AS participant_id,
        TRY_TO_NUMBER(p.value:teamId::STRING) AS team_id,
        TRY_TO_BOOLEAN(p.value:win::STRING) AS win,
        TRY_TO_NUMBER(p.value:kills::STRING) AS kills,
        TRY_TO_NUMBER(p.value:deaths::STRING) AS deaths,
        TRY_TO_NUMBER(p.value:assists::STRING) AS assists,
        TRY_TO_NUMBER(p.value:totalMinionsKilled::STRING) AS lane_cs,
        TRY_TO_NUMBER(p.value:neutralMinionsKilled::STRING) AS jungle_cs,
        TRY_TO_NUMBER(p.value:goldEarned::STRING) AS gold,
        TRY_TO_NUMBER(p.value:totalDamageDealtToChampions::STRING) AS champion_damage,
        TRY_TO_NUMBER(p.value:visionScore::STRING) AS vision
    FROM RIFTLAB.RAW.MATCHES m,
        LATERAL FLATTEN(INPUT => m.payload:info:participants, OUTER => TRUE) p
)
SELECT
    COUNT(*) AS flattened_rows_including_empty,
    COALESCE(COUNT_IF(COALESCE(TYPEOF(participant), 'SQL_NULL') <> 'OBJECT'), 0)
        AS invalid_participant_objects,
    COALESCE(COUNT_IF(puuid IS NULL), 0) AS missing_puuid,
    COALESCE(COUNT_IF(participant_id IS NULL OR team_id IS NULL), 0) AS invalid_keys,
    COALESCE(COUNT_IF(win IS NULL), 0) AS missing_or_invalid_win,
    COALESCE(COUNT_IF(kills IS NULL OR deaths IS NULL OR assists IS NULL), 0) AS invalid_kda,
    COALESCE(COUNT_IF(lane_cs IS NULL OR jungle_cs IS NULL), 0) AS invalid_cs,
    COALESCE(COUNT_IF(gold IS NULL), 0) AS invalid_gold,
    COALESCE(COUNT_IF(champion_damage IS NULL), 0) AS invalid_champion_damage,
    COALESCE(COUNT_IF(vision IS NULL), 0) AS invalid_vision,
    COALESCE(COUNT_IF(
        kills < 0 OR deaths < 0 OR assists < 0 OR lane_cs < 0 OR jungle_cs < 0
        OR gold < 0 OR champion_damage < 0 OR vision < 0
    ), 0) AS rows_with_negative_stats
FROM participants;

-- 4. Rôles et signaux de fin anticipée, pour définir les exclusions et l'appariement.
-- Aucun PUUID ni nom de joueur affiché dans les résultats.
SELECT
    TRY_TO_NUMBER(m.payload:info:queueId::STRING) AS queue_id,
    NULLIF(TRIM(p.value:teamPosition::STRING), '') AS team_position,
    TRY_TO_BOOLEAN(p.value:gameEndedInEarlySurrender::STRING) AS early_surrender,
    TRY_TO_BOOLEAN(p.value:gameEndedInSurrender::STRING) AS surrender,
    COUNT(*) AS participant_rows
FROM RIFTLAB.RAW.MATCHES m,
    LATERAL FLATTEN(INPUT => m.payload:info:participants) p
GROUP BY 1, 2, 3, 4
ORDER BY queue_id, team_position, early_surrender, surrender;

-- 5. Identifiants participants répétés dans un match : aucune ligne attendue.
-- Les doublons RAW sont aussi visibles ici ; les résoudre d'abord avec l'audit 03.
SELECT
    m.payload:metadata:matchId::STRING AS match_id,
    TRY_TO_NUMBER(p.value:participantId::STRING) AS participant_id,
    COUNT(*) AS participant_rows
FROM RIFTLAB.RAW.MATCHES m,
    LATERAL FLATTEN(INPUT => m.payload:info:participants) p
GROUP BY 1, 2
HAVING participant_id IS NULL OR COUNT(*) > 1
ORDER BY match_id, participant_id;

-- 6. Couverture temporelle de chaque timeline. frameInterval et timestamp sont en ms.
-- MAX seul ne prouve pas qu'une frame existe à 10/15 min : vérifier la section 7.
SELECT
    t.payload:metadata:matchId::STRING AS match_id,
    t.source_file,
    t.loaded_at,
    TRY_TO_NUMBER(t.payload:info:frameInterval::STRING) AS frame_interval_ms,
    ARRAY_SIZE(t.payload:info:frames) AS declared_frame_count,
    COUNT(f.index) AS observed_frame_count,
    MIN(TRY_TO_NUMBER(f.value:timestamp::STRING)) AS first_frame_ms,
    MAX(TRY_TO_NUMBER(f.value:timestamp::STRING)) AS last_frame_ms,
    COALESCE(COUNT_IF(
        f.index IS NOT NULL AND TRY_TO_NUMBER(f.value:timestamp::STRING) IS NULL
    ), 0) AS invalid_timestamps
FROM RIFTLAB.RAW.TIMELINES t,
    LATERAL FLATTEN(INPUT => t.payload:info:frames, OUTER => TRUE) f
GROUP BY 1, 2, 3, 4, 5
ORDER BY match_id;

-- 7. Candidats aux checkpoints : dernier snapshot <= cible, retard <= 60 secondes.
-- Diagnostic au niveau frame, pas encore au niveau participant. Une frame retenue
-- doit ensuite contenir les statistiques du participant. La durée du match sera
-- également vérifiée dans le futur modèle ; cette requête ne valide pas l'éligibilité.
WITH targets AS (
    SELECT column1 AS checkpoint_minute, column1 * 60000 AS target_ms
    FROM VALUES (10), (15)
), candidates AS (
    SELECT
        t.payload:metadata:matchId::STRING AS match_id,
        t.source_file,
        t.loaded_at,
        c.checkpoint_minute,
        c.target_ms,
        TRY_TO_NUMBER(f.value:timestamp::STRING) AS frame_timestamp_ms
    FROM RIFTLAB.RAW.TIMELINES t
    CROSS JOIN targets c,
        LATERAL FLATTEN(INPUT => t.payload:info:frames, OUTER => TRUE) f
)
SELECT
    match_id,
    source_file,
    loaded_at,
    checkpoint_minute,
    MAX(IFF(frame_timestamp_ms BETWEEN target_ms - 60000 AND target_ms,
        frame_timestamp_ms, NULL)) AS selected_frame_ms,
    target_ms - selected_frame_ms AS lag_ms,
    IFF(selected_frame_ms IS NULL, 'NO_ADMISSIBLE_FRAME', 'FRAME_AVAILABLE') AS frame_status
FROM candidates
GROUP BY match_id, source_file, loaded_at, checkpoint_minute, target_ms
ORDER BY match_id, checkpoint_minute;

-- 8. Qualité des statistiques temporelles ; compteurs d'anomalies attendus à zéro.
WITH participant_frames AS (
    SELECT
        pf.value AS participant_frame,
        TRY_TO_NUMBER(pf.value:participantId::STRING) AS participant_id,
        TRY_TO_NUMBER(pf.value:totalGold::STRING) AS total_gold,
        TRY_TO_NUMBER(pf.value:xp::STRING) AS xp,
        TRY_TO_NUMBER(pf.value:minionsKilled::STRING) AS lane_cs,
        TRY_TO_NUMBER(pf.value:jungleMinionsKilled::STRING) AS jungle_cs
    FROM RIFTLAB.RAW.TIMELINES t,
        LATERAL FLATTEN(INPUT => t.payload:info:frames) f,
        LATERAL FLATTEN(INPUT => f.value:participantFrames, OUTER => TRUE) pf
)
SELECT
    COUNT(*) AS flattened_rows_including_empty,
    COALESCE(COUNT_IF(COALESCE(TYPEOF(participant_frame), 'SQL_NULL') <> 'OBJECT'), 0)
        AS invalid_participant_frame_objects,
    COALESCE(COUNT_IF(participant_id IS NULL), 0) AS invalid_participant_ids,
    COALESCE(COUNT_IF(total_gold IS NULL), 0) AS invalid_total_gold,
    COALESCE(COUNT_IF(xp IS NULL), 0) AS invalid_xp,
    COALESCE(COUNT_IF(lane_cs IS NULL OR jungle_cs IS NULL), 0) AS invalid_cs,
    COALESCE(COUNT_IF(total_gold < 0 OR xp < 0 OR lane_cs < 0 OR jungle_cs < 0), 0)
        AS rows_with_negative_stats
FROM participant_frames;

-- Décision de fin d'audit : périmètre queue/carte, durée, exclusions, qualité des rôles,
-- traitement des doublons et couverture des timelines à inscrire dans le bilan.

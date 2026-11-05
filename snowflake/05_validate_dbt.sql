-- À exécuter après un Build réussi dans Snowsight avec la cible dev du profil riftlab.
-- Adapter les noms de schéma si le préfixe DBT_DEV du profil change.
-- Lecture seule, sauf la variable locale de session target_puuid.
USE ROLE SYSADMIN;
USE WAREHOUSE RIFTLAB_WH;
USE DATABASE RIFTLAB;

-- 1. Volumes : le fait doit contenir autant de lignes que les participants.
SELECT 'STG_MATCHES' AS model_name, COUNT(*) AS row_count
FROM RIFTLAB.DBT_DEV_STAGING.STG_MATCHES
UNION ALL
SELECT 'STG_TIMELINES', COUNT(*) FROM RIFTLAB.DBT_DEV_STAGING.STG_TIMELINES
UNION ALL
SELECT 'INT_MATCH_PARTICIPANTS', COUNT(*)
FROM RIFTLAB.DBT_DEV_INTERMEDIATE.INT_MATCH_PARTICIPANTS
UNION ALL
SELECT 'INT_MATCH_TEAMS', COUNT(*) FROM RIFTLAB.DBT_DEV_INTERMEDIATE.INT_MATCH_TEAMS
UNION ALL
SELECT 'FCT_PLAYER_MATCHES', COUNT(*) FROM RIFTLAB.DBT_DEV_MARTS.FCT_PLAYER_MATCHES;

-- 2. Comprendre les exclusions avant toute interprétation des moyennes.
SELECT
    eligibility_reason,
    COUNT(*) AS participant_rows,
    COUNT(DISTINCT match_id) AS match_count
FROM RIFTLAB.DBT_DEV_MARTS.FCT_PLAYER_MATCHES
GROUP BY eligibility_reason
ORDER BY eligibility_reason;

-- 3. Remplacer uniquement cette valeur, localement, par le PUUID du joueur suivi.
-- Un PUUID non remplacé donne zéro partie ; ce n'est pas une validation du résultat.
SET target_puuid = 'REMPLACER_PAR_LE_PUUID_DU_JOUEUR';

-- 4. Synthèse personnelle, sur toutes les parties éligibles de ce joueur.
SELECT
    COUNT(*) AS games_played,
    COALESCE(COUNT_IF(win), 0) AS wins,
    100.0 * COALESCE(COUNT_IF(win), 0) / NULLIF(COUNT(*), 0) AS win_rate_pct,
    AVG(kills) AS avg_kills,
    AVG(deaths) AS avg_deaths,
    AVG(assists) AS avg_assists,
    AVG(kda) AS avg_kda,
    AVG(cs_per_minute) AS avg_cs_per_minute,
    AVG(gold_per_minute) AS avg_gold_per_minute,
    AVG(champion_damage_per_minute) AS avg_champion_damage_per_minute,
    AVG(vision_per_minute) AS avg_vision_per_minute,
    AVG(kill_participation_pct) AS avg_kill_participation_pct,
    COUNT(kill_participation_pct) AS games_with_kill_participation,
    AVG(team_damage_share_pct) AS avg_team_damage_share_pct,
    COUNT(team_damage_share_pct) AS games_with_damage_share
FROM RIFTLAB.DBT_DEV_MARTS.FCT_PLAYER_MATCHES
WHERE is_kpi_eligible AND puuid = $target_puuid;

-- 5. Parties à rapprocher des JSON sources pour la recette manuelle.
SELECT
    match_id, game_start_utc, champion_name, role, win,
    duration_minutes, kills, deaths, assists,
    kda, cs_per_minute, gold_per_minute, champion_damage_per_minute,
    vision_per_minute, kill_participation_pct, team_damage_share_pct,
    is_kpi_eligible, eligibility_reason
FROM RIFTLAB.DBT_DEV_MARTS.FCT_PLAYER_MATCHES
WHERE puuid = $target_puuid
ORDER BY game_start_utc DESC, match_id
LIMIT 10;

-- Requête de recette : choisir le PUUID dans une session locale, ne pas le versionner.
-- dbt compile produit le SQL sous target/compiled/riftlab/analyses/.
-- Dans Snowsight, lancer d'abord : SET target_puuid = '<PUUID_DU_JOUEUR>';
select
    count(*) as games_played,
    coalesce(count_if(win), 0) as wins,
    100.0 * coalesce(count_if(win), 0) / nullif(count(*), 0) as win_rate_pct,
    avg(kills) as avg_kills,
    avg(deaths) as avg_deaths,
    avg(assists) as avg_assists,
    avg(kda) as avg_kda,
    avg(cs_per_minute) as avg_cs_per_minute,
    avg(gold_per_minute) as avg_gold_per_minute,
    avg(champion_damage_per_minute) as avg_champion_damage_per_minute,
    avg(vision_per_minute) as avg_vision_per_minute,
    avg(kill_participation_pct) as avg_kill_participation_pct,
    count(kill_participation_pct) as games_with_kill_participation,
    avg(team_damage_share_pct) as avg_team_damage_share_pct,
    count(team_damage_share_pct) as games_with_damage_share,
    avg(duration_minutes) as avg_duration_minutes
from {{ ref('fct_player_matches') }}
where is_kpi_eligible
    and puuid = $target_puuid

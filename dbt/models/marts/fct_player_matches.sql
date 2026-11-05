with match_eligibility as (
    select
        match_id,
        count(*) as participant_count,
        count(distinct team_id) as team_count,
        case
            when count_if(early_surrender) > 0 then true
            when count(early_surrender) = count(*) then false
            else null
        end as match_early_surrender
    from {{ ref('int_match_participants') }}
    group by match_id
), base as (
    select
        p.*,
        m.game_start_utc,
        m.duration_seconds,
        m.duration_seconds / 60.0 as duration_minutes,
        m.queue_id,
        m.map_id,
        m.patch,
        m.source_file,
        m.loaded_at,
        t.team_kills,
        t.team_champion_damage,
        case
            when m.queue_id is null or m.map_id is null then 'UNKNOWN_MODE'
            when m.queue_id <> {{ var('kpi_queue_id') }}
                or m.map_id <> {{ var('kpi_map_id') }} then 'OUT_OF_SCOPE'
            when m.duration_seconds is null or m.duration_seconds <= 0 then 'INVALID_DURATION'
            when e.participant_count <> 10 or e.team_count <> 2 then 'INVALID_ROSTER'
            when e.match_early_surrender then 'EARLY_SURRENDER'
            when e.match_early_surrender is null then 'UNKNOWN_EARLY_SURRENDER'
            when p.win is null then 'MISSING_RESULT'
            else 'ELIGIBLE'
        end as eligibility_reason
    from {{ ref('int_match_participants') }} p
    inner join {{ ref('stg_matches') }} m on p.match_id = m.match_id
    left join {{ ref('int_match_teams') }} t
        on p.match_id = t.match_id and p.team_id = t.team_id
    left join match_eligibility e on p.match_id = e.match_id
)
select
    *,
    eligibility_reason = 'ELIGIBLE' as is_kpi_eligible,
    (kills + assists) / greatest(1, deaths)::float as kda,
    (lane_cs + jungle_cs) / iff(duration_minutes > 0, duration_minutes, null) as cs_per_minute,
    gold_earned / iff(duration_minutes > 0, duration_minutes, null) as gold_per_minute,
    champion_damage / iff(duration_minutes > 0, duration_minutes, null)
        as champion_damage_per_minute,
    vision_score / iff(duration_minutes > 0, duration_minutes, null) as vision_per_minute,
    100.0 * (kills + assists) / nullif(team_kills, 0) as kill_participation_pct,
    100.0 * champion_damage / nullif(team_champion_damage, 0) as team_damage_share_pct
from base

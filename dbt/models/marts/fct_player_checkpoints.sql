{{ config(materialized='table') }}

with checkpoints as (
    select column1::string as checkpoint_code, column2::integer as checkpoint_minute
    from values
        ('M03', 3), ('M05', 5), ('M10', 10), ('M15', 15),
        ('M20', 20), ('M30', 30), ('FINAL', null)
), match_targets as (
    select
        m.match_id,
        c.checkpoint_code,
        c.checkpoint_minute,
        m.duration_seconds * 1000 as match_end_ms,
        coalesce(c.checkpoint_minute * 60, m.duration_seconds) * 1000 as target_timestamp_ms
    from {{ ref('stg_matches') }} m
    cross join checkpoints c
), frame_times as (
    select distinct match_id, frame_timestamp_ms
    from {{ ref('int_participant_frames') }}
), closest_frames as (
    select
        t.*,
        f.frame_timestamp_ms,
        l.match_id is not null as has_timeline
    from match_targets t
    left join frame_times f
        on t.match_id = f.match_id
        and t.target_timestamp_ms <= t.match_end_ms
        and abs(f.frame_timestamp_ms - t.target_timestamp_ms) <= 5000
    left join {{ ref('stg_timelines') }} l on t.match_id = l.match_id
    qualify row_number() over (
        partition by t.match_id, t.checkpoint_code
        order by abs(f.frame_timestamp_ms - t.target_timestamp_ms), f.frame_timestamp_ms
    ) = 1
), player_points as (
    select
        p.match_id,
        p.participant_id,
        p.puuid,
        p.team_id,
        p.role,
        p.champion_id,
        p.champion_name,
        p.patch,
        p.game_start_utc,
        p.is_kpi_eligible,
        p.eligibility_reason,
        c.checkpoint_code,
        c.checkpoint_minute,
        c.target_timestamp_ms,
        f.frame_timestamp_ms,
        f.frame_timestamp_ms - c.target_timestamp_ms as frame_offset_ms,
        case
            when c.match_end_ms is null or c.match_end_ms <= 0 then 'INVALID_DURATION'
            when c.checkpoint_code = 'FINAL' then 'AVAILABLE'
            when c.target_timestamp_ms > c.match_end_ms then 'MATCH_ENDED'
            when not c.has_timeline then 'NO_TIMELINE'
            when c.frame_timestamp_ms is null then 'NO_NEARBY_FRAME'
            when f.participant_id is null then 'NO_PARTICIPANT_FRAME'
            else 'AVAILABLE'
        end as checkpoint_status,
        iff(c.checkpoint_code = 'FINAL', p.gold_earned, f.total_gold) as total_gold,
        iff(c.checkpoint_code = 'FINAL', p.lane_cs + p.jungle_cs, f.total_cs) as total_cs,
        f.xp,
        iff(c.checkpoint_code = 'FINAL', p.win, null) as win
    from {{ ref('fct_player_matches') }} p
    join closest_frames c on p.match_id = c.match_id
    left join {{ ref('int_participant_frames') }} f
        on p.match_id = f.match_id
        and p.participant_id = f.participant_id
        and c.frame_timestamp_ms = f.frame_timestamp_ms
), unique_team_roles as (
    select match_id, team_id, role, min(participant_id) as participant_id
    from {{ ref('int_match_participants') }}
    where role in ('TOP', 'JUNGLE', 'MIDDLE', 'BOTTOM', 'UTILITY')
    group by match_id, team_id, role
    having count(*) = 1
)
select
    p.*,
    r.participant_id as opponent_participant_id,
    p.total_gold - o.total_gold as gold_diff,
    p.total_cs - o.total_cs as cs_diff,
    p.xp - o.xp as xp_diff
from player_points p
left join unique_team_roles r
    on p.is_kpi_eligible and p.match_id = r.match_id
    and p.team_id <> r.team_id and p.role = r.role
left join player_points o
    on p.match_id = o.match_id and r.participant_id = o.participant_id
    and p.checkpoint_code = o.checkpoint_code
    and p.checkpoint_status = 'AVAILABLE' and o.checkpoint_status = 'AVAILABLE'

with checkpoint_counts as (
    select match_id, participant_id, count(*) as point_count
    from {{ ref('fct_player_checkpoints') }}
    group by match_id, participant_id
)
select p.match_id, p.participant_id, 'CHECKPOINT_COUNT' as failure
from {{ ref('fct_player_matches') }} p
left join checkpoint_counts c using (match_id, participant_id)
where coalesce(c.point_count, 0) <> 7

union all

select match_id, participant_id, 'CHECKPOINT_MEASUREMENT' as failure
from {{ ref('fct_player_checkpoints') }}
where abs(frame_offset_ms) > 5000
    or (checkpoint_code <> 'FINAL' and checkpoint_status = 'AVAILABLE'
        and frame_timestamp_ms is null)
    or (checkpoint_code <> 'FINAL' and checkpoint_status <> 'AVAILABLE'
        and (total_gold is not null or total_cs is not null or xp is not null))

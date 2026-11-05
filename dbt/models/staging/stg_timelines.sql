with normalized as (
    select
        nullif(trim(payload:metadata:matchId::string), '') as match_id,
        payload,
        source_file,
        loaded_at
    from {{ source('riot_raw', 'timelines') }}
)
select
    match_id,
    try_to_number(payload:info:frameInterval::string) as frame_interval_ms,
    payload:info:frames as frames,
    source_file,
    loaded_at
from normalized
qualify row_number() over (
    partition by match_id
    order by loaded_at desc nulls last, source_file desc nulls last,
        sha2(to_json(payload), 256) desc
) = 1

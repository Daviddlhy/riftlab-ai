with normalized as (
    select
        nullif(trim(payload:metadata:matchId::string), '') as match_id,
        payload,
        source_file,
        loaded_at
    from {{ source('riot_raw', 'matches') }}
), deduplicated as (
    select *
    from normalized
    qualify row_number() over (
        partition by match_id
        order by loaded_at desc nulls last, source_file desc nulls last,
            sha2(to_json(payload), 256) desc
    ) = 1
)
select
    match_id,
    try_to_number(payload:info:queueId::string) as queue_id,
    try_to_number(payload:info:mapId::string) as map_id,
    payload:info:gameMode::string as game_mode,
    payload:info:gameVersion::string as game_version,
    split_part(payload:info:gameVersion::string, '.', 1) || '.'
        || split_part(payload:info:gameVersion::string, '.', 2) as patch,
    to_timestamp_ntz(try_to_number(payload:info:gameStartTimestamp::string), 3)
        as game_start_utc,
    try_to_number(payload:info:gameDuration::string) as duration_seconds,
    payload:info:participants as participants,
    payload:info:teams as teams,
    source_file,
    loaded_at
from deduplicated

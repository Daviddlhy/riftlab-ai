{{ config(materialized='table') }}

select
    t.match_id,
    try_to_number(p.key::string) as participant_id,
    try_to_number(f.value:timestamp::string) as frame_timestamp_ms,
    try_to_number(p.value:totalGold::string) as total_gold,
    try_to_number(p.value:minionsKilled::string)
        + try_to_number(p.value:jungleMinionsKilled::string) as total_cs,
    try_to_number(p.value:xp::string) as xp
from {{ ref('stg_timelines') }} t,
    lateral flatten(input => t.frames) f,
    lateral flatten(input => f.value:participantFrames) p

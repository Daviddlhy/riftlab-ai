-- Détecter les pertes et multiplications de lignes entre JSON, participants et faits.
with participants as (
    select match_id, count(*) as row_count
    from {{ ref('int_match_participants') }}
    group by match_id
), facts as (
    select match_id, count(*) as row_count
    from {{ ref('fct_player_matches') }}
    group by match_id
)
select m.match_id
from {{ ref('stg_matches') }} m
left join participants p on m.match_id = p.match_id
left join facts f on m.match_id = f.match_id
where coalesce(array_size(m.participants), 0) = 0
    or coalesce(p.row_count, 0) <> array_size(m.participants)
    or coalesce(f.row_count, 0) <> array_size(m.participants)

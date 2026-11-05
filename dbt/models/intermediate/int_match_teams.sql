with team_stats as (
    select
        match_id,
        team_id,
        count(*) as participant_count,
        -- Un champ manquant doit invalider le total, pas sous-estimer le dénominateur.
        iff(count(kills) = count(*), sum(kills), null) as team_kills,
        iff(count(champion_damage) = count(*), sum(champion_damage), null)
            as team_champion_damage,
        -- Un signal absent n'est pas interprété comme false.
        case
            when count_if(early_surrender) > 0 then true
            when count(early_surrender) = count(*) then false
            else null
        end as team_early_surrender
    from {{ ref('int_match_participants') }}
    group by match_id, team_id
), teams as (
    select
        m.match_id,
        try_to_number(t.value:teamId::string) as team_id,
        try_to_boolean(t.value:win::string) as win
    from {{ ref('stg_matches') }} m,
        lateral flatten(input => m.teams) t
)
select
    t.match_id,
    t.team_id,
    t.win,
    s.participant_count,
    s.team_kills,
    s.team_champion_damage,
    s.team_early_surrender
from teams t
left join team_stats s
    on t.match_id = s.match_id and t.team_id = s.team_id

-- Chaque participant doit référencer une équipe réelle et le même résultat.
select p.match_id, p.participant_id
from {{ ref('int_match_participants') }} p
left join {{ ref('int_match_teams') }} t
    on p.match_id = t.match_id and p.team_id = t.team_id
where t.team_id is null or p.win is distinct from t.win

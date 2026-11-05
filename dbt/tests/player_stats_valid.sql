select match_id, participant_id
from {{ ref('fct_player_matches') }}
where kills is null or deaths is null or assists is null
    or lane_cs is null or jungle_cs is null or gold_earned is null
    or champion_damage is null or vision_score is null
    or kills < 0 or deaths < 0 or assists < 0
    or lane_cs < 0 or jungle_cs < 0 or gold_earned < 0
    or champion_damage < 0 or vision_score < 0
    or kill_participation_pct not between 0 and 100
    or team_damage_share_pct not between 0 and 100

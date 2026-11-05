-- La déduplication ne doit pas masquer des identifiants RAW invalides.
select 'matches' as source_name, source_file
from {{ source('riot_raw', 'matches') }}
where nullif(trim(payload:metadata:matchId::string), '') is null
union all
select 'timelines', source_file
from {{ source('riot_raw', 'timelines') }}
where nullif(trim(payload:metadata:matchId::string), '') is null

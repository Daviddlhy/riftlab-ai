select 'matches' as source_name
from {{ source('riot_raw', 'matches') }}
having count(*) = 0
union all
select 'timelines'
from {{ source('riot_raw', 'timelines') }}
having count(*) = 0

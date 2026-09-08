-- Assert no orphaned attending staff on admissions
select a.admission_id
from {{ source('warehouse', 'admissions') }} a
left join {{ source('warehouse', 'staff') }} s
  on a.attending_staff_id = s.staff_id
where a.attending_staff_id is not null
  and s.staff_id is null

{{ config(materialized='view') }}

select
  p.patient_id,
  p.patient_status,
  s.staff_id as primary_care_staff_id
from {{ source('warehouse', 'patients') }} p
left join {{ source('warehouse', 'staff') }} s
  on p.primary_care_staff_id = s.staff_id
where p.primary_care_staff_id is not null
  and s.staff_id is null

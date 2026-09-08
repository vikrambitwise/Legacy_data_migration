{{ config(materialized='view') }}

select *
from {{ source('warehouse', 'patients') }}
where patient_status not in ('Active', 'Discharged', 'Inactive', 'Suspended')
  and patient_status is not null

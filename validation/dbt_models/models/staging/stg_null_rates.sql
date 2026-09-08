{{ config(materialized='view') }}

select
  'patients' as table_name,
  'patient_status' as column_name,
  avg(case when patient_status is null then 1.0 else 0.0 end) as null_rate
from {{ source('warehouse', 'patients') }}
union all
select
  'admissions',
  'discharge_date',
  avg(case when discharge_date is null then 1.0 else 0.0 end)
from {{ source('warehouse', 'admissions') }}
union all
select
  'invoices',
  'billing_status',
  avg(case when billing_status is null then 1.0 else 0.0 end)
from {{ source('warehouse', 'invoices') }}

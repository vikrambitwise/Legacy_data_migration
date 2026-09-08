{{ config(materialized='view') }}

select 'departments' as table_name, count(*) as row_count from {{ source('warehouse', 'departments') }}
union all
select 'staff', count(*) from {{ source('warehouse', 'staff') }}
union all
select 'patients', count(*) from {{ source('warehouse', 'patients') }}
union all
select 'admissions', count(*) from {{ source('warehouse', 'admissions') }}
union all
select 'encounters', count(*) from {{ source('warehouse', 'encounters') }}
union all
select 'invoices', count(*) from {{ source('warehouse', 'invoices') }}
union all
select 'lab_results', count(*) from {{ source('warehouse', 'lab_results') }}

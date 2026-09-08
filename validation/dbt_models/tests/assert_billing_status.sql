-- Closed-set business rule for billing_status
select invoice_id, billing_status
from {{ source('warehouse', 'invoices') }}
where billing_status is not null
  and billing_status not in ('Draft', 'Submitted', 'Paid', 'Void')

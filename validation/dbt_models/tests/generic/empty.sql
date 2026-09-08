-- Generic empty-relation check used when dbt_utils is not packaged.
{% test empty(model) %}
  select 1 as fail_row from {{ model }} limit 1
{% endtest %}

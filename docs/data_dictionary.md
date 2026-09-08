# Target Data Dictionary

Canonical documentation generated from approved mappings and transformation rules.

## admissions

### `admission_id`

Primary key adm_id copied to admission_id.

- **Lineage:** admit_events.adm_id -> admissions.admission_id via src (prompt rule_generation_v1:prompt-df87a038537b)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-94225394ee38`

### `patient_id`

Legacy column admit_events.pat_id migrated to admissions.patient_id.

- **Lineage:** admit_events.pat_id -> admissions.patient_id via src (prompt rule_generation_v1:prompt-6252797c5519)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-9ccecbe526b4`

### `admit_date`

Legacy column admit_events.admit_dt migrated to admissions.admit_date.

- **Lineage:** admit_events.admit_dt -> admissions.admit_date via src (prompt rule_generation_v1:prompt-5349d4cabe06)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-ecfe73f46d28`

### `discharge_date`

Discharge date stored as VARCHAR with mixed formats (ISO, US, compact).

- **Lineage:** admit_events.dsch_dt -> admissions.discharge_date via TO_DATE(src) (prompt rule_generation_v1:prompt-e13e08be49b5)
- **Transformation:** `TO_DATE(src)`
- **Human override:** Approved via CLI with confidence 0.64; inferred meaning accepted: Discharge date stored as VARCHAR with mixed formats (ISO, US, compact).
- **Prompt ID:** `doc_generation_v1:prompt-28b2281213e1`

### `admission_type`

Undocumented code column adm_typ with observed values ['I', 'O', 'E']. Labels are inferred from sample patterns and naming conventions — not from source documentation.

- **Lineage:** admit_events.adm_typ -> admissions.admission_type via CASE WHEN src = 'I' THEN 'Inpatient' WHEN src = 'O' THEN 'Outpatient' WHEN src = 'E' THEN 'Emergency' ELSE NULL END (prompt rule_generation_v1:prompt-d44fa9833a2d)
- **Transformation:** `CASE WHEN src = 'I' THEN 'Inpatient' WHEN src = 'O' THEN 'Outpatient' WHEN src = 'E' THEN 'Emergency' ELSE NULL END`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-99351fa51965`

### `department_id`

Legacy column admit_events.dept_id migrated to admissions.department_id.

- **Lineage:** admit_events.dept_id -> admissions.department_id via src (prompt rule_generation_v1:prompt-a71fdccc1f7d)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-8da5b0c7cc92`

### `attending_staff_id`

Legacy column admit_events.attending_id migrated to admissions.attending_staff_id.

- **Lineage:** admit_events.attending_id -> admissions.attending_staff_id via src (prompt rule_generation_v1:prompt-82b5a478dd44)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-977613a35811`

## invoices

### `invoice_id`

Primary key txn_id copied to invoice_id.

- **Lineage:** billing_txns.txn_id -> invoices.invoice_id via src (prompt rule_generation_v1:prompt-43b5dad4507b)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-e43c03d36134`

### `patient_id`

Legacy column billing_txns.pat_id migrated to invoices.patient_id.

- **Lineage:** billing_txns.pat_id -> invoices.patient_id via src (prompt rule_generation_v1:prompt-c1eee4166103)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-9a2d2d45ff9f`

### `encounter_id`

Legacy column billing_txns.enc_id migrated to invoices.encounter_id.

- **Lineage:** billing_txns.enc_id -> invoices.encounter_id via src (prompt rule_generation_v1:prompt-8b1bbacc49cc)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-120f6d262583`

### `amount`

Legacy column billing_txns.amt migrated to invoices.amount.

- **Lineage:** billing_txns.amt -> invoices.amount via src (prompt rule_generation_v1:prompt-d1dd1f3e408f)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-1553ca23aca2`

### `billing_status`

Undocumented code column bill_st with observed values ['0', '1', '2', '9']. Labels are inferred from sample patterns and naming conventions — not from source documentation.

- **Lineage:** billing_txns.bill_st -> invoices.billing_status via CASE WHEN src = '0' THEN 'Draft' WHEN src = '1' THEN 'Submitted' WHEN src = '2' THEN 'Paid' WHEN src = '9' THEN 'Void' ELSE NULL END (prompt rule_generation_v1:prompt-55ccbc6bdb99)
- **Transformation:** `CASE WHEN src = '0' THEN 'Draft' WHEN src = '1' THEN 'Submitted' WHEN src = '2' THEN 'Paid' WHEN src = '9' THEN 'Void' ELSE NULL END`
- **Human override:** Approved via CLI with confidence 0.72; inferred meaning accepted: Undocumented code column bill_st with observed values ['0', '1', '2', '9']. Labels are inferred from sample patterns and naming conventions — not from source documentation.
- **Prompt ID:** `doc_generation_v1:prompt-b263dee03c4f`

### `paid_date`

Legacy column billing_txns.paid_dt migrated to invoices.paid_date.

- **Lineage:** billing_txns.paid_dt -> invoices.paid_date via src (prompt rule_generation_v1:prompt-7e4956c940df)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-b0f60c065710`

### `cpt_code`

Legacy column billing_txns.cpt_cd migrated to invoices.cpt_code.

- **Lineage:** billing_txns.cpt_cd -> invoices.cpt_code via src (prompt rule_generation_v1:prompt-d39ef479eb0b)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-e49aec6344f0`

## encounters

### `encounter_id`

Primary key enc_id copied to encounter_id.

- **Lineage:** encounters.enc_id -> encounters.encounter_id via src (prompt rule_generation_v1:prompt-773a9fda3554)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-bd7bdea1ec2c`

### `patient_id`

Legacy column encounters.pat_id migrated to encounters.patient_id.

- **Lineage:** encounters.pat_id -> encounters.patient_id via src (prompt rule_generation_v1:prompt-61804ae0853f)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-1e6344e1d72e`

### `admission_id`

Legacy column encounters.adm_id migrated to encounters.admission_id.

- **Lineage:** encounters.adm_id -> encounters.admission_id via src (prompt rule_generation_v1:prompt-3f4f67a86525)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-aea4aae72e5a`

### `encounter_date`

Legacy column encounters.enc_dt migrated to encounters.encounter_date.

- **Lineage:** encounters.enc_dt -> encounters.encounter_date via src (prompt rule_generation_v1:prompt-4b943f2d01a8)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-0da39d541c6a`

### `encounter_type`

Legacy column encounters.enc_typ migrated to encounters.encounter_type.

- **Lineage:** encounters.enc_typ -> encounters.encounter_type via src (prompt rule_generation_v1:prompt-e0910bdb5676)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-453d99602a59`

### `notes`

Legacy column encounters.notes_txt migrated to encounters.notes.

- **Lineage:** encounters.notes_txt -> encounters.notes via src (prompt rule_generation_v1:prompt-213e26116d36)
- **Transformation:** `src`
- **Human override:** Approved via CLI with confidence 0.74; inferred meaning accepted: Legacy column encounters.notes_txt migrated to encounters.notes.
- **Prompt ID:** `doc_generation_v1:prompt-fcbc56f69f71`

## lab_results

### `result_id`

Primary key rslt_id copied to result_id.

- **Lineage:** lab_rslts.rslt_id -> lab_results.result_id via src (prompt rule_generation_v1:prompt-78e03ecefaa9)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-eb4b3786e586`

### `patient_id`

Legacy column lab_rslts.pat_id migrated to lab_results.patient_id.

- **Lineage:** lab_rslts.pat_id -> lab_results.patient_id via src (prompt rule_generation_v1:prompt-88a12a7992cf)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-05cc87792b45`

### `encounter_id`

Legacy column lab_rslts.enc_id migrated to lab_results.encounter_id.

- **Lineage:** lab_rslts.enc_id -> lab_results.encounter_id via src (prompt rule_generation_v1:prompt-99a7eebee8af)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-04f03e777168`

### `test_code`

Legacy column lab_rslts.test_cd migrated to lab_results.test_code.

- **Lineage:** lab_rslts.test_cd -> lab_results.test_code via src (prompt rule_generation_v1:prompt-d4870a20b3ac)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-5fa369baebfd`

### `result_value`

Legacy column lab_rslts.rslt_val migrated to lab_results.result_value.

- **Lineage:** lab_rslts.rslt_val -> lab_results.result_value via src (prompt rule_generation_v1:prompt-a8fe9e1a62b7)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-9374f483c385`

### `unit_of_measure`

Legacy column lab_rslts.rslt_uom migrated to lab_results.unit_of_measure.

- **Lineage:** lab_rslts.rslt_uom -> lab_results.unit_of_measure via src (prompt rule_generation_v1:prompt-3cb18f2e0a05)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-af67f8bae0a5`

### `is_abnormal`

Undocumented code column abn_flg with observed values ['0', '1']. Labels are inferred from sample patterns and naming conventions — not from source documentation.

- **Lineage:** lab_rslts.abn_flg -> lab_results.is_abnormal via CASE WHEN src = '0' THEN 'false' WHEN src = '1' THEN 'true' ELSE NULL END (prompt rule_generation_v1:prompt-7d299b25d27c)
- **Transformation:** `CASE WHEN src = '0' THEN 'false' WHEN src = '1' THEN 'true' ELSE NULL END`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-1d1f6159b0c5`

### `collected_date`

Legacy column lab_rslts.coll_dt migrated to lab_results.collected_date.

- **Lineage:** lab_rslts.coll_dt -> lab_results.collected_date via src (prompt rule_generation_v1:prompt-838d70e391aa)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-412194887559`

## patients

### `patient_id`

Primary key pat_id copied to patient_id.

- **Lineage:** patient_records.pat_id -> patients.patient_id via src (prompt rule_generation_v1:prompt-c7be134cb9c5)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-644da8be9ada`

### `patient_name`

Legacy column patient_records.pat_nm migrated to patients.patient_name.

- **Lineage:** patient_records.pat_nm -> patients.patient_name via src (prompt rule_generation_v1:prompt-9f1820fb3001)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-760df7740d44`

### `date_of_birth`

Legacy column patient_records.dob migrated to patients.date_of_birth.

- **Lineage:** patient_records.dob -> patients.date_of_birth via src (prompt rule_generation_v1:prompt-dd5ec14a470e)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-09f7aeeeb7ac`

### `sex`

Undocumented code column sex_cd with observed values ['M', 'F', 'U']. Labels are inferred from sample patterns and naming conventions — not from source documentation.

- **Lineage:** patient_records.sex_cd -> patients.sex via CASE WHEN src = 'M' THEN 'Male' WHEN src = 'F' THEN 'Female' WHEN src = 'U' THEN 'Unknown' ELSE NULL END (prompt rule_generation_v1:prompt-64cfedb85628)
- **Transformation:** `CASE WHEN src = 'M' THEN 'Male' WHEN src = 'F' THEN 'Female' WHEN src = 'U' THEN 'Unknown' ELSE NULL END`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-8f16df7cfa6d`

### `patient_status`

Undocumented code column pat_st_cd with observed values ['A', 'D', 'I', 'S']. Labels are inferred from sample patterns and naming conventions — not from source documentation.

- **Lineage:** patient_records.pat_st_cd -> patients.patient_status via CASE WHEN src = 'A' THEN 'Active' WHEN src = 'D' THEN 'Discharged' WHEN src = 'I' THEN 'Inactive' WHEN src = 'S' THEN 'Suspended' ELSE NULL END (prompt rule_generation_v1:prompt-7b55e4da4611)
- **Transformation:** `CASE WHEN src = 'A' THEN 'Active' WHEN src = 'D' THEN 'Discharged' WHEN src = 'I' THEN 'Inactive' WHEN src = 'S' THEN 'Suspended' ELSE NULL END`
- **Human override:** Approved via CLI with confidence 0.72; inferred meaning accepted: Undocumented code column pat_st_cd with observed values ['A', 'D', 'I', 'S']. Labels are inferred from sample patterns and naming conventions — not from source documentation.
- **Prompt ID:** `doc_generation_v1:prompt-eb01d4c81ae1`

### `primary_care_staff_id`

Legacy column patient_records.pcp_stf_id migrated to patients.primary_care_staff_id.

- **Lineage:** patient_records.pcp_stf_id -> patients.primary_care_staff_id via src (prompt rule_generation_v1:prompt-c2b835c9916d)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-e901383a9359`

### `zip_code`

Legacy column patient_records.zip_cd migrated to patients.zip_code.

- **Lineage:** patient_records.zip_cd -> patients.zip_code via src (prompt rule_generation_v1:prompt-7e08c5d59076)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-2734e31b404d`

### `ssn_last4`

Legacy column patient_records.ssn_last4 migrated to patients.ssn_last4.

- **Lineage:** patient_records.ssn_last4 -> patients.ssn_last4 via src (prompt rule_generation_v1:prompt-3b06f410407a)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-8afa4041462b`

### `created_at`

Legacy column patient_records.created_ts migrated to patients.created_at.

- **Lineage:** patient_records.created_ts -> patients.created_at via src (prompt rule_generation_v1:prompt-1e9796d25354)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-fd5d8d5f57a2`

## departments

### `department_id`

Primary key dept_id copied to department_id.

- **Lineage:** ref_dept.dept_id -> departments.department_id via src (prompt rule_generation_v1:prompt-3ea91b8b376e)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-c0c86aefa9cd`

### `department_name`

Legacy column ref_dept.dept_nm migrated to departments.department_name.

- **Lineage:** ref_dept.dept_nm -> departments.department_name via src (prompt rule_generation_v1:prompt-91d2c0df938e)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-774b695727be`

### `location_code`

Legacy column ref_dept.loc_cd migrated to departments.location_code.

- **Lineage:** ref_dept.loc_cd -> departments.location_code via src (prompt rule_generation_v1:prompt-8b71bfb76be6)
- **Transformation:** `src`
- **Human override:** Approved via CLI with confidence 0.74; inferred meaning accepted: Legacy column ref_dept.loc_cd migrated to departments.location_code.
- **Prompt ID:** `doc_generation_v1:prompt-3de595aeff34`

### `is_active`

Undocumented code column actv_flg with observed values ['Y', 'N']. Labels are inferred from sample patterns and naming conventions — not from source documentation.

- **Lineage:** ref_dept.actv_flg -> departments.is_active via CASE WHEN src = 'Y' THEN 'true' WHEN src = 'N' THEN 'false' ELSE NULL END (prompt rule_generation_v1:prompt-31a5a48a0aa6)
- **Transformation:** `CASE WHEN src = 'Y' THEN 'true' WHEN src = 'N' THEN 'false' ELSE NULL END`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-a530fe117072`

## staff

### `staff_id`

Primary key stf_id copied to staff_id.

- **Lineage:** staff_mst.stf_id -> staff.staff_id via src (prompt rule_generation_v1:prompt-46bc87499407)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-716477aaab75`

### `staff_name`

Legacy column staff_mst.stf_nm migrated to staff.staff_name.

- **Lineage:** staff_mst.stf_nm -> staff.staff_name via src (prompt rule_generation_v1:prompt-b0e3ba6fb3c9)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-1034077cd15b`

### `department_id`

Legacy column staff_mst.dept_id migrated to staff.department_id.

- **Lineage:** staff_mst.dept_id -> staff.department_id via src (prompt rule_generation_v1:prompt-1e06817b6b35)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-faeb35040cf5`

### `role_code`

Undocumented code column role_cd with observed values ['MD', 'RN', 'AD', 'TH']. Labels are inferred from sample patterns and naming conventions — not from source documentation.

- **Lineage:** staff_mst.role_cd -> staff.role_code via CASE WHEN src = 'MD' THEN 'Physician' WHEN src = 'RN' THEN 'Nurse' WHEN src = 'AD' THEN 'Admin' WHEN src = 'TH' THEN 'Therapist' ELSE NULL END (prompt rule_generation_v1:prompt-eb81e1ec65db)
- **Transformation:** `CASE WHEN src = 'MD' THEN 'Physician' WHEN src = 'RN' THEN 'Nurse' WHEN src = 'AD' THEN 'Admin' WHEN src = 'TH' THEN 'Therapist' ELSE NULL END`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-b9e1fe126b13`

### `hire_date`

Legacy column staff_mst.hire_dt migrated to staff.hire_date.

- **Lineage:** staff_mst.hire_dt -> staff.hire_date via src (prompt rule_generation_v1:prompt-9f3f0bab92b8)
- **Transformation:** `src`
- **Human override:** _none_
- **Prompt ID:** `doc_generation_v1:prompt-a3d10ec263f6`

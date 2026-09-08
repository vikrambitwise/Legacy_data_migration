import pandas as pd

from core.models import TransformationRule
from etl.transforms import apply_rule


def test_status_code_mapping():
    rule = TransformationRule(
        source_column="pat_st_cd",
        target_column="patient_status",
        logic="CASE WHEN src = 'A' THEN 'Active' WHEN src = 'D' THEN 'Discharged' ELSE NULL END",
        null_handling="Map to NULL",
        edge_cases=["Unknown codes default to NULL", "Trim whitespace before mapping"],
        confidence=0.84,
        prompt_id="p1",
        source_table="patient_records",
        target_table="patients",
        mapping_dict={"A": "Active", "D": "Discharged"},
        transform_type="map",
    )
    series = pd.Series(["A", " D", "X", None, ""])
    out = apply_rule(series, rule)
    assert list(out) == ["Active", "Discharged", None, None, None]


def test_mixed_date_parsing():
    rule = TransformationRule(
        source_column="dsch_dt",
        target_column="discharge_date",
        logic="TO_DATE(src)",
        null_handling="empty string to NULL",
        edge_cases=[],
        confidence=0.64,
        prompt_id="p2",
        source_table="admit_events",
        target_table="admissions",
        transform_type="date",
    )
    series = pd.Series(["2023-01-15", "01/15/2023", "20230115", "", None])
    out = apply_rule(series, rule)
    assert out.tolist()[0] == "2023-01-15"
    assert out.tolist()[1] == "2023-01-15"
    assert out.tolist()[2] == "2023-01-15"
    assert out.tolist()[3] is None

from core.models import TransformationRule
from review.human_review import UnapprovedMappingError
from etl.migration_executor import MigrationExecutor
from pathlib import Path


def _rule(**kwargs):
    base = dict(
        source_column="pat_st_cd",
        target_column="patient_status",
        logic="CASE WHEN src = 'A' THEN 'Active' ELSE NULL END",
        null_handling="Map to NULL; flag in reconciliation report.",
        edge_cases=["Unknown codes default to NULL"],
        confidence=0.84,
        prompt_id="prompt-test",
        human_reviewed=False,
        override_note=None,
        source_table="patient_records",
        target_table="patients",
        mapping_dict={"A": "Active"},
        transform_type="map",
    )
    base.update(kwargs)
    return TransformationRule(**base)


def test_high_confidence_rule_is_executable():
    assert _rule(confidence=0.84).is_approved_for_execution(0.80)


def test_low_confidence_without_review_is_blocked():
    rule = _rule(confidence=0.72, human_reviewed=False, override_note=None)
    assert not rule.is_approved_for_execution(0.80)


def test_low_confidence_with_review_and_note_is_allowed():
    rule = _rule(confidence=0.72, human_reviewed=True, override_note="Domain expert: D=Discharged")
    assert rule.is_approved_for_execution(0.80)


def test_spec_fields_present():
    payload = _rule().to_spec_dict()
    assert set(payload) >= {
        "source_column",
        "target_column",
        "logic",
        "null_handling",
        "edge_cases",
        "confidence",
        "prompt_id",
        "human_reviewed",
        "override_note",
    }


def test_executor_blocks_unapproved_rules(tmp_path: Path):
    executor = MigrationExecutor("run-test", tmp_path)
    try:
        executor._assert_executable([_rule(confidence=0.5, human_reviewed=False)])
        assert False, "should have blocked"
    except UnapprovedMappingError:
        pass

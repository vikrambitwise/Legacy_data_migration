from core.graph import topological_load_order
from core.pii import detect_pii


def test_load_order_parents_before_children():
    graph = {
        "patient_records": ["staff_mst"],
        "staff_mst": ["ref_dept"],
        "admit_events": ["patient_records", "ref_dept"],
        "ref_dept": [],
    }
    order = topological_load_order(graph, list(graph))
    assert order.index("ref_dept") < order.index("staff_mst")
    assert order.index("staff_mst") < order.index("patient_records")
    assert order.index("patient_records") < order.index("admit_events")


def test_pii_flags_on_legacy_columns():
    assert "person_name" in detect_pii("pat_nm", ["Ava Reed"])
    assert "date_of_birth" in detect_pii("dob", ["1960-01-01"])
    assert "national_id" in detect_pii("ssn_last4", ["1234"])

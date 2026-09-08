"""Create and seed the synthetic legacy OLTP schema (assessment data only)."""

from __future__ import annotations

import argparse
import random
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

from core.config import ROOT, get_settings
from core.logging import get_logger
from connectors.db import get_source_engine

logger = get_logger("source.seed")

FIRST = [
    "Ava", "Noah", "Mia", "Liam", "Emma", "Olivia", "Elena", "James", "Sofia", "Lucas",
    "Priya", "Omar", "Chen", "Amara", "Diego", "Hana", "Jonah", "Leila", "Mateo", "Nora",
]
LAST = [
    "Reed", "Patel", "Nguyen", "Garcia", "Khan", "Silva", "Wright", "Okoro", "Berg", "Cho",
    "Ibrahim", "Santos", "Murphy", "Kowalski", "Yamamoto", "Ali", "Rossi", "Andersen", "Diaz", "Park",
]
DEPTS = [
    (1, "Cardiology", "N"),
    (2, "Oncology", "E"),
    (3, "Pediatrics", "S"),
    (4, "Emergency", "W"),
    (5, "Radiology", "N"),
    (6, "Orthopedics", "E"),
    (7, "Neurology", "S"),
    (8, "General Medicine", "W"),
    (9, "Surgery", "N"),
    (10, "Lab Services", "E"),
    (11, "Billing Ops", "S"),
    (12, "Pharmacy", "W"),
]
ROLES = ["MD", "RN", "AD", "TH"]
PAT_STATUS = ["A", "A", "A", "A", "D", "D", "I", "S"]
SEX = ["M", "F", "F", "M", "U"]
ADM_TYP = ["I", "O", "O", "E"]
ENC_TYP = ["OFFICE", "INPT", "ER", "TELE"]
BILL_ST = [0, 1, 1, 2, 2, 2, 9]
TEST_CD = ["CBC", "BMP", "HBA1C", "LIPID", "TSH", "PTINR"]
DATE_FORMATS = ["iso", "us", "compact", "empty"]

POSTGRES_DDL = """
DROP TABLE IF EXISTS lab_rslts CASCADE;
DROP TABLE IF EXISTS billing_txns CASCADE;
DROP TABLE IF EXISTS encounters CASCADE;
DROP TABLE IF EXISTS admit_events CASCADE;
DROP TABLE IF EXISTS patient_records CASCADE;
DROP TABLE IF EXISTS staff_mst CASCADE;
DROP TABLE IF EXISTS ref_dept CASCADE;

CREATE TABLE ref_dept (
    dept_id   INTEGER PRIMARY KEY,
    dept_nm   VARCHAR(64) NOT NULL,
    loc_cd    CHAR(1),
    actv_flg  CHAR(1)
);

CREATE TABLE staff_mst (
    stf_id    INTEGER PRIMARY KEY,
    stf_nm    VARCHAR(120) NOT NULL,
    dept_id   INTEGER REFERENCES ref_dept(dept_id),
    role_cd   VARCHAR(8),
    hire_dt   DATE
);

CREATE TABLE patient_records (
    pat_id      INTEGER PRIMARY KEY,
    pat_nm      VARCHAR(120) NOT NULL,
    dob         DATE,
    sex_cd      CHAR(1),
    pat_st_cd   VARCHAR(2),
    pcp_stf_id  INTEGER REFERENCES staff_mst(stf_id),
    zip_cd      VARCHAR(10),
    ssn_last4   VARCHAR(4),
    created_ts  TIMESTAMP NOT NULL
);

CREATE TABLE admit_events (
    adm_id        INTEGER PRIMARY KEY,
    pat_id        INTEGER NOT NULL REFERENCES patient_records(pat_id),
    admit_dt      DATE,
    dsch_dt       VARCHAR(16),
    adm_typ       CHAR(1),
    dept_id       INTEGER REFERENCES ref_dept(dept_id),
    attending_id  INTEGER REFERENCES staff_mst(stf_id)
);

CREATE TABLE encounters (
    enc_id     INTEGER PRIMARY KEY,
    pat_id     INTEGER NOT NULL REFERENCES patient_records(pat_id),
    adm_id     INTEGER REFERENCES admit_events(adm_id),
    enc_dt     DATE,
    enc_typ    VARCHAR(12),
    notes_txt  VARCHAR(240)
);

CREATE TABLE billing_txns (
    txn_id   INTEGER PRIMARY KEY,
    pat_id   INTEGER NOT NULL REFERENCES patient_records(pat_id),
    enc_id   INTEGER REFERENCES encounters(enc_id),
    amt      NUMERIC(10,2),
    bill_st  INTEGER,
    paid_dt  DATE,
    cpt_cd   VARCHAR(8)
);

CREATE TABLE lab_rslts (
    rslt_id   INTEGER PRIMARY KEY,
    pat_id    INTEGER NOT NULL REFERENCES patient_records(pat_id),
    enc_id    INTEGER REFERENCES encounters(enc_id),
    test_cd   VARCHAR(12),
    rslt_val  VARCHAR(24),
    rslt_uom  VARCHAR(16),
    abn_flg   INTEGER,
    coll_dt   DATE
);
"""

SQLITE_DDL = POSTGRES_DDL.replace("CASCADE", "").replace("NUMERIC(10,2)", "REAL").replace("TIMESTAMP", "DATETIME")


def _name(rng: random.Random) -> str:
    return f"{rng.choice(FIRST)} {rng.choice(LAST)}"


def _format_discharge(rng: random.Random, admit: date, status: str) -> str | None:
    if status in {"A", "I", "S"} and rng.random() < 0.7:
        fmt = rng.choice(DATE_FORMATS)
        if fmt == "empty":
            return ""
        return None
    stay = timedelta(days=rng.randint(1, 21))
    discharged = admit + stay
    fmt = rng.choice(["iso", "iso", "us", "compact"])
    if fmt == "iso":
        return discharged.isoformat()
    if fmt == "us":
        return discharged.strftime("%m/%d/%Y")
    return discharged.strftime("%Y%m%d")


def seed(engine: Engine, patient_n: int = 12000, seed: int = 42) -> dict[str, int]:
    rng = random.Random(seed)
    dialect = engine.dialect.name
    ddl = SQLITE_DDL if dialect == "sqlite" else POSTGRES_DDL
    logger.info("Creating legacy schema dialect=%s patients=%s", dialect, patient_n)

    with engine.begin() as conn:
        for stmt in [s.strip() for s in ddl.split(";") if s.strip()]:
            conn.execute(text(stmt))

        conn.execute(
            text("INSERT INTO ref_dept (dept_id, dept_nm, loc_cd, actv_flg) VALUES (:id,:nm,:loc,:flg)"),
            [{"id": i, "nm": n, "loc": loc, "flg": "Y" if i < 12 else "N"} for i, n, loc in DEPTS],
        )

        staff_rows = []
        for stf_id in range(1, 201):
            staff_rows.append(
                {
                    "stf_id": stf_id,
                    "stf_nm": _name(rng),
                    "dept_id": rng.choice(DEPTS)[0] if rng.random() > 0.05 else None,
                    "role_cd": rng.choice(ROLES),
                    "hire_dt": date(2005, 1, 1) + timedelta(days=rng.randint(0, 7000)),
                }
            )
        conn.execute(
            text(
                "INSERT INTO staff_mst (stf_id, stf_nm, dept_id, role_cd, hire_dt) "
                "VALUES (:stf_id,:stf_nm,:dept_id,:role_cd,:hire_dt)"
            ),
            staff_rows,
        )

        patients = []
        base_day = datetime(2018, 1, 1)
        for pat_id in range(1, patient_n + 1):
            status = rng.choice(PAT_STATUS)
            if rng.random() < 0.008:
                status = rng.choice(["X", " "])
            patients.append(
                {
                    "pat_id": pat_id,
                    "pat_nm": _name(rng),
                    "dob": date(1935, 1, 1) + timedelta(days=rng.randint(0, 25000)),
                    "sex_cd": rng.choice(SEX),
                    "pat_st_cd": status,
                    "pcp_stf_id": rng.randint(1, 200) if rng.random() > 0.12 else None,
                    "zip_cd": f"{rng.randint(10000, 99999)}",
                    "ssn_last4": f"{rng.randint(0, 9999):04d}",
                    "created_ts": base_day + timedelta(days=rng.randint(0, 2800), seconds=rng.randint(0, 86400)),
                }
            )
        _bulk(conn, "patient_records", patients)

        admits = []
        adm_id = 1
        for pat in patients:
            n_adm = 1 if rng.random() < 0.7 else rng.randint(0, 3)
            for _ in range(n_adm):
                admit_dt = date(2019, 1, 1) + timedelta(days=rng.randint(0, 2400))
                admits.append(
                    {
                        "adm_id": adm_id,
                        "pat_id": pat["pat_id"],
                        "admit_dt": admit_dt,
                        "dsch_dt": _format_discharge(rng, admit_dt, pat["pat_st_cd"]),
                        "adm_typ": rng.choice(ADM_TYP),
                        "dept_id": rng.choice(DEPTS)[0],
                        "attending_id": rng.randint(1, 200) if rng.random() > 0.18 else None,
                    }
                )
                adm_id += 1
        _bulk(conn, "admit_events", admits)

        encounters = []
        enc_id = 1
        admits_by_pat: dict[int, list[int]] = {}
        for row in admits:
            admits_by_pat.setdefault(row["pat_id"], []).append(row["adm_id"])
        for pat in patients:
            n_enc = rng.randint(1, 4)
            for _ in range(n_enc):
                cand = admits_by_pat.get(pat["pat_id"], [])
                encounters.append(
                    {
                        "enc_id": enc_id,
                        "pat_id": pat["pat_id"],
                        "adm_id": rng.choice(cand) if cand and rng.random() > 0.25 else None,
                        "enc_dt": date(2019, 1, 1) + timedelta(days=rng.randint(0, 2400)),
                        "enc_typ": rng.choice(ENC_TYP),
                        "notes_txt": rng.choice(
                            [None, "f/u needed", "pt stable", "awaiting labs", ""]
                        )
                        if rng.random() < 0.4
                        else None,
                    }
                )
                enc_id += 1
        _bulk(conn, "encounters", encounters)

        bills = []
        txn_id = 1
        encs_by_pat: dict[int, list[int]] = {}
        for row in encounters:
            encs_by_pat.setdefault(row["pat_id"], []).append(row["enc_id"])
        for pat in patients:
            n_txn = rng.randint(0, 3)
            for _ in range(n_txn):
                st = rng.choice(BILL_ST)
                bills.append(
                    {
                        "txn_id": txn_id,
                        "pat_id": pat["pat_id"],
                        "enc_id": rng.choice(encs_by_pat.get(pat["pat_id"], [None])),
                        "amt": round(rng.uniform(25, 18000), 2),
                        "bill_st": st,
                        "paid_dt": (
                            date(2020, 1, 1) + timedelta(days=rng.randint(0, 2000))
                            if st == 2
                            else None
                        ),
                        "cpt_cd": f"{rng.randint(99201, 99499)}",
                    }
                )
                txn_id += 1
        _bulk(conn, "billing_txns", bills)

        labs = []
        rslt_id = 1
        for pat in patients:
            n_lab = rng.randint(0, 3)
            for _ in range(n_lab):
                labs.append(
                    {
                        "rslt_id": rslt_id,
                        "pat_id": pat["pat_id"],
                        "enc_id": rng.choice(encs_by_pat.get(pat["pat_id"], [None])),
                        "test_cd": rng.choice(TEST_CD),
                        "rslt_val": str(round(rng.uniform(0.4, 18.0), 2)),
                        "rslt_uom": rng.choice(["mg/dL", "mmol/L", "%", "IU/L"]),
                        "abn_flg": 1 if rng.random() < 0.12 else 0,
                        "coll_dt": date(2019, 6, 1) + timedelta(days=rng.randint(0, 2200)),
                    }
                )
                rslt_id += 1
        _bulk(conn, "lab_rslts", labs)

    counts = {
        "ref_dept": len(DEPTS),
        "staff_mst": len(staff_rows),
        "patient_records": len(patients),
        "admit_events": len(admits),
        "encounters": len(encounters),
        "billing_txns": len(bills),
        "lab_rslts": len(labs),
    }
    logger.info("Seed complete: %s", counts)
    return counts


def _bulk(conn, table: str, rows: list[dict]) -> None:
    if not rows:
        return
    cols = list(rows[0].keys())
    placeholders = ",".join(f":{c}" for c in cols)
    stmt = text(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})")
    chunk = 1000
    for i in range(0, len(rows), chunk):
        conn.execute(stmt, rows[i : i + chunk])


def ensure_sqlite_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        sqlite3.connect(path).close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed synthetic legacy source database")
    parser.add_argument("--patients", type=int, default=12000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    settings = get_settings()
    url = settings.source_db_url
    if url.startswith("sqlite"):
        db_path = url.split("///")[-1]
        ensure_sqlite_file(ROOT / db_path if not Path(db_path).is_absolute() else Path(db_path))
    elif url.startswith("postgresql"):
        from source.bootstrap_postgres import ensure_from_source_url

        ensure_from_source_url(url)
    engine = get_source_engine(url)
    seed(engine, patient_n=args.patients, seed=args.seed)


if __name__ == "__main__":
    main()

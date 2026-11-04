import csv
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("review_labels", ROOT / "eval" / "review_labels.py")
review_labels = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review_labels)


def read_rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_sheet_hides_gold_labels(tmp_path):
    sheet = tmp_path / "sheet.csv"
    review_labels.write_sheet(sheet)
    rows = read_rows(sheet)
    assert "gold_verdict" not in rows[0]
    assert all(row["verdict"] == "" for row in rows)


def test_sample_includes_ambiguous_cases_and_every_verdict():
    sample = review_labels.sample_cases(review_labels.all_cases())
    ids = {case["case_id"] for case in sample}
    assert {"HIT-103-CHG-1", "HIT-103-SEC-1", "HIT-105-DAT-1"} <= ids
    assert {case["gold_verdict"] for case in sample} == review_labels.VERDICTS


def test_kappa_values():
    assert review_labels.cohens_kappa(["a", "b"], ["a", "b"]) == pytest.approx(1.0)
    assert review_labels.cohens_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"]) == pytest.approx(0.0)


def test_agreement_rejects_blank_sheet(tmp_path, capsys):
    sheet = tmp_path / "sheet.csv"
    review_labels.write_sheet(sheet)
    assert review_labels.report_agreement(sheet) == 1
    assert "invalid verdict" in capsys.readouterr().out


def filled_rows(tmp_path):
    gold = {case["case_id"]: case["gold_verdict"] for case in review_labels.all_cases()}
    sheet = tmp_path / "sheet.csv"
    review_labels.write_sheet(sheet)
    return [{**row, "verdict": gold[row["case_id"]]} for row in read_rows(sheet)]


def write_rows(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def test_agreement_rejects_duplicate_case(tmp_path, capsys):
    rows = filled_rows(tmp_path)
    rows[1] = dict(rows[0])
    sheet = tmp_path / "filled.csv"
    write_rows(sheet, rows)
    assert review_labels.report_agreement(sheet) == 1
    output = capsys.readouterr().out
    assert "appears more than once" in output
    assert "missing from the sheet" in output


def test_agreement_rejects_omitted_case(tmp_path, capsys):
    sheet = tmp_path / "filled.csv"
    write_rows(sheet, filled_rows(tmp_path)[:-1])
    assert review_labels.report_agreement(sheet) == 1
    assert "missing from the sheet" in capsys.readouterr().out


def test_agreement_rejects_case_outside_sample(tmp_path, capsys):
    rows = filled_rows(tmp_path)
    sampled = {row["case_id"] for row in rows}
    other = next(c for c in review_labels.all_cases() if c["case_id"] not in sampled)
    rows.append({**rows[0], "case_id": other["case_id"], "verdict": other["gold_verdict"]})
    sheet = tmp_path / "filled.csv"
    write_rows(sheet, rows)
    assert review_labels.report_agreement(sheet) == 1
    assert "not in the expected sample" in capsys.readouterr().out


def test_agreement_reports_perfect_match(tmp_path, capsys):
    gold = {case["case_id"]: case["gold_verdict"] for case in review_labels.all_cases()}
    sheet = tmp_path / "sheet.csv"
    review_labels.write_sheet(sheet)
    rows = read_rows(sheet)
    with sheet.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "verdict": gold[row["case_id"]]})
    assert review_labels.report_agreement(sheet) == 0
    assert "100%" in capsys.readouterr().out

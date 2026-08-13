"""Merge auto-passed records with completed human adjudications, then build auditable raw-label mappings.

The reviewed/adjudicated controlled categories are authoritative. Raw-label mapping files are
created for traceability and optional harmonization; they do not overwrite the reviewed paper-level
taxonomy assignments.
"""

import csv
import json
from collections import Counter
from pathlib import Path

from common import (
    OUTPUT_DIR,
    read_jsonl,
    write_jsonl,
    write_csv,
    load_json,
    normalize_list,
    canonical_list,
    get_row_id,
    index_rows,
)

PRIMARY_JSONL = OUTPUT_DIR / "03_primary_content_extraction.jsonl"
AUTO_PASSED_JSONL = OUTPUT_DIR / "04_auto_passed_extractions.jsonl"
HUMAN_REPORT_CSV = OUTPUT_DIR / "04_human_review_report.csv"
HUMAN_COMPLETED_CSV = OUTPUT_DIR / "04_human_adjudication_completed.csv"

ADJUDICATED_JSONL = OUTPUT_DIR / "05_adjudicated_extractions.jsonl"
ADJUDICATED_CSV = OUTPUT_DIR / "05_adjudicated_extractions.csv"

DATA_TYPES_MAP_CSV = OUTPUT_DIR / "05_data_type_mapping_for_review.csv"
ALGORITHMS_MAP_CSV = OUTPUT_DIR / "05_algorithm_mapping_for_review.csv"

devices = load_json("consumer_wearable_devices.json")
domains = load_json("health_domains.json")
data_taxonomy = load_json("data_type_taxonomy.json")
algorithm_taxonomy = load_json("algorithm_taxonomy.json")


def load_csv(path):
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def parse_json_list_or_keep(cell, current, allowed):
    cell = (cell or "").strip()
    if not cell:
        return canonical_list(current, allowed)
    try:
        value = json.loads(cell)
    except Exception as exc:
        raise ValueError(f"Expected a JSON list but got {cell!r}") from exc
    if not isinstance(value, list):
        raise ValueError(f"Expected JSON list, got {type(value).__name__}: {cell!r}")
    invalid = [x for x in value if x not in allowed]
    if invalid:
        raise ValueError(f"Invalid controlled labels: {invalid}")
    return canonical_list(value, allowed)


def collect_data_types(row):
    values = []
    values.extend(normalize_list(row.get("wearable_data_types_raw", [])))
    for device_row in row.get("device_extractions", []) or []:
        if isinstance(device_row, dict):
            values.extend(normalize_list(device_row.get("wearable_data_types_raw", [])))
    return values


def simple_suggestion(raw_label, taxonomy):
    raw = raw_label.lower().strip()

    for choice in taxonomy:
        c = choice.lower().strip()
        if raw == c or raw in c or c in raw:
            return choice

    rules = {
        "steps": "Step count",
        "step count": "Step count",
        "spo2": "Blood oxygen saturation",
        "oxygen saturation": "Blood oxygen saturation",
        "eda": "Electrodermal activity",
        "electrodermal": "Electrodermal activity",
        "hrv": "Heart rate variability",
        "heart rate variability": "Heart rate variability",
        "ppg": "PPG",
        "photoplethysm": "PPG",
        "acceler": "Accelerometer",
        "gyro": "Gyroscope / orientation",
        "orientation": "Gyroscope / orientation",
        "sleep duration": "Sleep duration/Time in bed",
        "time in bed": "Sleep duration/Time in bed",
        "sleep quality": "Sleep quality metrics",
        "sleep stage": "Sleep stages",
        "awakening": "Awakening count",
        "respiratory rate": "Respiratory rate",
        "energy expenditure": "Energy expenditure",
        "caloric intake": "Caloric intake",
        "calorie intake": "Caloric intake",
        "metabolic equivalent": "Metabolic equivalent",
        "circadian": "Circadian rhythm",
        "random forest": "Tree-based and ensemble ML",
        "xgboost": "Tree-based and ensemble ML",
        "gradient boost": "Tree-based and ensemble ML",
        "decision tree": "Tree-based and ensemble ML",
        "regression": "Regression and statistical modeling",
        "mixed-effects": "Regression and statistical modeling",
        "neural": "Deep learning and neural networks",
        "cnn": "Deep learning and neural networks",
        "lstm": "Deep learning and neural networks",
        "svm": "Classical non-tree supervised ML",
        "support vector": "Classical non-tree supervised ML",
        "k-nearest": "Classical non-tree supervised ML",
        "knn": "Classical non-tree supervised ML",
        "rule-based": "Rule-based and heuristic algorithms",
        "threshold": "Rule-based and heuristic algorithms",
        "signal processing": "Signal processing and feature engineering",
        "feature extraction": "Signal processing and feature engineering",
        "anomaly": "Anomaly and change detection",
        "change detection": "Anomaly and change detection",
        "cluster": "Unsupervised clustering and latent-variable methods",
        "pca": "Unsupervised clustering and latent-variable methods",
        "hidden markov": "Sequential probabilistic and state-space models",
        "state-space": "Sequential probabilistic and state-space models",
        "bayesian filter": "Sequential probabilistic and state-space models",
        "transformer": "Transformer, attention, and foundation models",
        "attention": "Transformer, attention, and foundation models",
        "foundation model": "Transformer, attention, and foundation models",
        "llm": "Transformer, attention, and foundation models",
    }

    for key, value in rules.items():
        if key in raw and value in taxonomy:
            return value
    return ""


primary_rows = read_jsonl(PRIMARY_JSONL)
primary_by_id = index_rows(primary_rows)
auto_rows = read_jsonl(AUTO_PASSED_JSONL) if AUTO_PASSED_JSONL.exists() else []

human_report = load_csv(HUMAN_REPORT_CSV)
flagged_ids = {
    str(r.get("PMID") or r.get("source_pdf") or "").strip()
    for r in human_report
    if str(r.get("PMID") or r.get("source_pdf") or "").strip()
}

adjudicated_rows = []

if flagged_ids:
    if not HUMAN_COMPLETED_CSV.exists():
        raise SystemExit(
            f"{len(flagged_ids)} records require human adjudication. Complete "
            f"outputs/04_human_adjudication_template.csv and save it as "
            f"{HUMAN_COMPLETED_CSV.name} before running step 05."
        )

    completed = load_csv(HUMAN_COMPLETED_CSV)
    completed_by_id = {
        str(r.get("PMID") or r.get("source_pdf") or "").strip(): r
        for r in completed
        if str(r.get("PMID") or r.get("source_pdf") or "").strip()
    }

    missing = sorted(x for x in flagged_ids if x not in completed_by_id)
    if missing:
        raise SystemExit(f"Missing completed human adjudication rows for: {missing[:20]}")

    for row_id in sorted(flagged_ids):
        human = completed_by_id[row_id]
        if str(human.get("adjudication_status", "")).strip().lower() not in {
            "resolved", "complete", "completed"
        }:
            raise SystemExit(f"Human adjudication for {row_id} is not marked Resolved/Complete.")

        if row_id not in primary_by_id:
            raise SystemExit(f"Could not find primary extraction for human-adjudicated ID: {row_id}")

        primary = dict(primary_by_id[row_id])

        primary["health_domains"] = parse_json_list_or_keep(
            human.get("final_health_domains_json"), primary.get("health_domains"), domains
        )
        primary["consumer_wearables_used"] = parse_json_list_or_keep(
            human.get("final_consumer_wearables_used_json"),
            primary.get("consumer_wearables_used"),
            devices,
        )
        primary["data_type_taxonomy_categories"] = parse_json_list_or_keep(
            human.get("final_data_type_taxonomy_categories_json"),
            primary.get("data_type_taxonomy_categories"),
            data_taxonomy,
        )

        alg_status = (human.get("final_algorithm_developed") or "").strip()
        if alg_status:
            if alg_status not in {"Yes", "No", "Not sure"}:
                raise ValueError(f"Invalid final_algorithm_developed for {row_id}: {alg_status}")
            primary["algorithm_developed"] = alg_status

        primary["algorithm_taxonomy_categories"] = parse_json_list_or_keep(
            human.get("final_algorithm_taxonomy_categories_json"),
            primary.get("algorithm_taxonomy_categories"),
            algorithm_taxonomy,
        )

        primary["multi_llm_review_disposition"] = "HUMAN_ADJUDICATED"
        primary["human_adjudication_notes"] = human.get("human_notes", "")
        adjudicated_rows.append(primary)

final_rows = auto_rows + adjudicated_rows

order = {get_row_id(row): i for i, row in enumerate(primary_rows)}
final_rows.sort(key=lambda r: order.get(get_row_id(r), 10**9))

if len(final_rows) != len(primary_rows):
    raise SystemExit(
        f"Final reviewed row count ({len(final_rows)}) does not match primary extraction count "
        f"({len(primary_rows)}). Check step 04/05 IDs."
    )

write_jsonl(ADJUDICATED_JSONL, final_rows)
write_csv(ADJUDICATED_CSV, final_rows)

data_counts = Counter()
algorithm_counts = Counter()

for row in final_rows:
    for label in collect_data_types(row):
        data_counts[label] += 1
    for label in normalize_list(row.get("algorithm_types_raw", [])):
        algorithm_counts[label] += 1

write_csv(
    DATA_TYPES_MAP_CSV,
    [
        {
            "raw_label": raw,
            "count": count,
            "suggested_standard_label": simple_suggestion(raw, data_taxonomy),
            "final_standard_label": simple_suggestion(raw, data_taxonomy),
            "review_notes": "",
        }
        for raw, count in data_counts.most_common()
    ],
)

write_csv(
    ALGORITHMS_MAP_CSV,
    [
        {
            "raw_label": raw,
            "count": count,
            "suggested_standard_label": simple_suggestion(raw, algorithm_taxonomy),
            "final_standard_label": simple_suggestion(raw, algorithm_taxonomy),
            "review_notes": "",
        }
        for raw, count in algorithm_counts.most_common()
    ],
)

print(f"Wrote reviewed/adjudicated extraction table:\n{ADJUDICATED_JSONL}\n{ADJUDICATED_CSV}")
print(f"Wrote optional raw-label mapping review files:\n{DATA_TYPES_MAP_CSV}\n{ALGORITHMS_MAP_CSV}")

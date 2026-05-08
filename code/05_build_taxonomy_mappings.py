"""Build candidate mapping tables from raw extracted data types and algorithms.
Edit the CSV outputs manually for human-in-the-loop adjudication before running step 06.
"""
from collections import Counter
from common import OUTPUT_DIR, read_jsonl, write_csv, load_json, normalize_list

INPUT_JSONL = OUTPUT_DIR / "03_primary_content_extraction.jsonl"
DATA_TYPES_MAP_CSV = OUTPUT_DIR / "05_data_type_mapping_for_review.csv"
ALGORITHMS_MAP_CSV = OUTPUT_DIR / "05_algorithm_mapping_for_review.csv"

data_taxonomy = load_json("data_type_taxonomy.json")
algorithm_taxonomy = load_json("algorithm_taxonomy.json")


def closest_label(raw_label, choices):
    raw = raw_label.lower().strip()
    for choice in choices:
        c = choice.lower().strip()
        if c == raw or c in raw or raw in c:
            return choice
    return ""


def collect_data_types(row):
    values = []
    values.extend(normalize_list(row.get("wearable_data_types_raw", [])))
    for device_row in row.get("device_extractions", []) or []:
        if isinstance(device_row, dict):
            values.extend(normalize_list(device_row.get("wearable_data_types_raw", [])))
    return values


data_type_counts = Counter()
algorithm_counts = Counter()
for row in read_jsonl(INPUT_JSONL):
    for label in collect_data_types(row):
        data_type_counts[label] += 1
    for label in normalize_list(row.get("algorithm_types_raw", [])):
        algorithm_counts[label] += 1

write_csv(
    DATA_TYPES_MAP_CSV,
    [
        {
            "raw_label": raw,
            "count": count,
            "suggested_standard_label": closest_label(raw, data_taxonomy),
            "final_standard_label": closest_label(raw, data_taxonomy),
            "review_notes": "",
        }
        for raw, count in data_type_counts.most_common()
    ],
)
write_csv(
    ALGORITHMS_MAP_CSV,
    [
        {
            "raw_label": raw,
            "count": count,
            "suggested_standard_label": closest_label(raw, algorithm_taxonomy),
            "final_standard_label": closest_label(raw, algorithm_taxonomy),
            "review_notes": "",
        }
        for raw, count in algorithm_counts.most_common()
    ],
)
print(f"Wrote mapping review files:\n{DATA_TYPES_MAP_CSV}\n{ALGORITHMS_MAP_CSV}")

"""Apply reviewed label mappings and add final LLM-assisted taxonomy categories.

This step intentionally preserves the existing standardized-label columns:
- data_types_standardized
- algorithm_types_standardized

It also adds paper-level taxonomy columns mapped to the controlled vocabularies in:
- configs/data_type_taxonomy.json
- configs/algorithm_taxonomy.json

New output columns:
- data_type_taxonomy_categories
- algorithm_taxonomy_categories
- data_type_taxonomy_label_map
- algorithm_taxonomy_label_map

The taxonomy mapping is attempted with the configured LLM model. If the LLM call is
not available, the script falls back to a conservative deterministic matcher so the
pipeline remains runnable during local testing.
"""

import csv
import json
from typing import Dict, Iterable, List

from common import (
    OUTPUT_DIR,
    read_jsonl,
    write_jsonl,
    write_csv,
    normalize_list,
    load_json,
    call_openai_json,
)

INPUT_JSONL = OUTPUT_DIR / "03_primary_content_extraction.jsonl"
DATA_TYPES_MAP_CSV = OUTPUT_DIR / "05_data_type_mapping_for_review.csv"
ALGORITHMS_MAP_CSV = OUTPUT_DIR / "05_algorithm_mapping_for_review.csv"
OUTPUT_JSONL = OUTPUT_DIR / "06_final_mapped_extractions.jsonl"
OUTPUT_CSV = OUTPUT_DIR / "06_final_mapped_extractions.csv"
DATA_TYPE_TAXONOMY_LLM_MAP_CSV = OUTPUT_DIR / "06_data_type_taxonomy_llm_mapping.csv"
ALGORITHM_TAXONOMY_LLM_MAP_CSV = OUTPUT_DIR / "06_algorithm_taxonomy_llm_mapping.csv"

DATA_TYPE_TAXONOMY = load_json("data_type_taxonomy.json")
ALGORITHM_TAXONOMY = load_json("algorithm_taxonomy.json")


def load_mapping(path):
    mapping = {}
    with path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            raw = row.get("raw_label", "").strip()
            final = row.get("final_standard_label", "").strip()
            if raw and final:
                mapping[raw] = final
    return mapping


def collect_data_types(row):
    values = []
    values.extend(normalize_list(row.get("wearable_data_types_raw", [])))
    for device_row in row.get("device_extractions", []) or []:
        if isinstance(device_row, dict):
            values.extend(normalize_list(device_row.get("wearable_data_types_raw", [])))
    return values


def mapped_unique(values, mapping):
    output = []
    for value in normalize_list(values):
        mapped = mapping.get(value, value)
        if mapped and mapped not in output:
            output.append(mapped)
    return output


def unique_preserve_order(values: Iterable[str]) -> List[str]:
    output = []
    for value in values:
        value = str(value).strip()
        if value and value not in output:
            output.append(value)
    return output


def deterministic_taxonomy_match(label: str, taxonomy: List[str]) -> str:
    """Conservative fallback matcher used only when the LLM is unavailable."""
    raw = label.lower().strip()
    if not raw:
        return ""

    # Exact or substring match against the configured taxonomy labels.
    for category in taxonomy:
        cat = category.lower().strip()
        if raw == cat or raw in cat or cat in raw:
            return category

    # Small, transparent synonym rules for common wearable-review terminology.
    synonyms = {
        "heart rate": "Heart rate",
        "bpm": "Heart rate",
        "rr interval": "Interbeat interval",
        "r-r interval": "Interbeat interval",
        "r–r interval": "Interbeat interval",
        "ibi": "Interbeat interval",
        "rmssd": "Heart rate variability",
        "hrv": "Heart rate variability",
        "photoplethysm": "PPG",
        "ppg": "PPG",
        "electrocard": "ECG",
        "ecg": "ECG",
        "acceler": "Accelerometer",
        "motion": "Accelerometer",
        "gyro": "Gyroscope/orientation",
        "orientation": "Gyroscope/orientation",
        "step": "Steps",
        "activity": "Physical activity",
        "sleep stage": "Sleep stages",
        "sleep duration": "Sleep duration/time in bed",
        "time in bed": "Sleep duration/time in bed",
        "sleep efficiency": "Sleep quality metrics",
        "sleep quality": "Sleep quality metrics",
        "sleep onset": "Sleep onset/offset",
        "wake-up": "Sleep onset/offset",
        "awakening": "Awakenings",
        "respiratory rate": "Respiratory rate",
        "spo2": "Blood oxygen saturation",
        "oxygen saturation": "Blood oxygen saturation",
        "blood oxygen": "Blood oxygen saturation",
        "temperature": "Temperature",
        "eda": "EDA",
        "electrodermal": "EDA",
        "energy expenditure": "Energy expenditure",
        "calorie": "Energy expenditure",
        "distance": "Distance/elevation/speed",
        "speed": "Distance/elevation/speed",
        "elevation": "Distance/elevation/speed",
        "cadence": "Cadence",
        "gps": "GPS/location",
        "location": "GPS/location",
        "wear time": "Wear time",
        "blood pressure": "Blood pressure",
        "body composition": "Body composition",
        "regression": "Regression/statistical models",
        "linear model": "Regression/statistical models",
        "generalized linear": "Regression/statistical models",
        "random forest": "Tree-based/ensemble machine learning",
        "gradient boost": "Tree-based/ensemble machine learning",
        "xgboost": "Tree-based/ensemble machine learning",
        "decision tree": "Tree-based/ensemble machine learning",
        "support vector": "Support vector machine",
        "svm": "Support vector machine",
        "neural": "Deep learning/neural networks",
        "deep learning": "Deep learning/neural networks",
        "cnn": "Convolutional neural network",
        "convolution": "Convolutional neural network",
        "lstm": "Recurrent neural network/LSTM",
        "recurrent": "Recurrent neural network/LSTM",
        "transformer": "Transformer/foundation model",
        "foundation model": "Transformer/foundation model",
        "cluster": "Clustering/unsupervised learning",
        "unsupervised": "Clustering/unsupervised learning",
        "feature extraction": "Signal processing/feature extraction",
        "signal processing": "Signal processing/feature extraction",
        "threshold": "Rule-based/threshold algorithm",
        "rule-based": "Rule-based/threshold algorithm",
        "descriptive": "Descriptive/statistical analysis",
        "bland-altman": "Descriptive/statistical analysis",
        "correlation": "Descriptive/statistical analysis",
        "t test": "Descriptive/statistical analysis",
        "chi-square": "Descriptive/statistical analysis",
        "mann-whitney": "Descriptive/statistical analysis",
    }
    for key, category in synonyms.items():
        if key in raw and category in taxonomy:
            return category
    return ""


def llm_map_labels_to_taxonomy(
    labels: List[str],
    taxonomy: List[str],
    label_type: str,
    output_cache_csv,
    batch_size: int = 80,
) -> Dict[str, str]:
    """Map free-text labels to configured taxonomy categories using the LLM.

    Returns a dictionary {input_label: taxonomy_category}. Unmapped labels are
    represented by an empty string. A CSV cache is written for transparent review.
    """
    labels = unique_preserve_order(labels)
    if not labels:
        return {}

    mapping: Dict[str, str] = {}
    used_fallback = False

    for start in range(0, len(labels), batch_size):
        batch = labels[start : start + batch_size]
        prompt = f"""
You are standardizing labels from a systematic review of consumer wearable studies.

Task:
Map each {label_type} label to exactly one category from the allowed taxonomy below.
Use an empty string if none of the allowed categories is a defensible match.
Do not invent categories. Preserve every input label exactly in the output.

Allowed taxonomy categories:
{json.dumps(taxonomy, ensure_ascii=False, indent=2)}

Input labels:
{json.dumps(batch, ensure_ascii=False, indent=2)}

Return valid JSON only, with this exact schema:
{{
  "mappings": [
    {{"input_label": "original label", "taxonomy_category": "one allowed category or empty string"}}
  ]
}}
""".strip()
        try:
            result = call_openai_json(prompt)
            returned = result.get("mappings", []) if isinstance(result, dict) else []
            for item in returned:
                input_label = str(item.get("input_label", "")).strip()
                category = str(item.get("taxonomy_category", "")).strip()
                if input_label in batch and category in taxonomy:
                    mapping[input_label] = category
                elif input_label in batch:
                    mapping[input_label] = ""
        except (Exception, SystemExit) as exc:
            used_fallback = True
            print(
                f"Warning: LLM taxonomy mapping failed for {label_type} batch "
                f"{start // batch_size + 1}; using deterministic fallback. Error: {exc}"
            )

        # Fill any missing labels from this batch with a conservative fallback.
        for label in batch:
            if label not in mapping:
                mapping[label] = deterministic_taxonomy_match(label, taxonomy)

    write_csv(
        output_cache_csv,
        [
            {
                "input_label": label,
                "taxonomy_category": mapping.get(label, ""),
                "mapping_method": "deterministic_fallback" if used_fallback else "llm",
            }
            for label in labels
        ],
    )
    return mapping


def taxonomy_categories_for_labels(labels: List[str], label_to_taxonomy: Dict[str, str]) -> List[str]:
    categories = []
    for label in labels:
        category = label_to_taxonomy.get(label, "")
        if category and category not in categories:
            categories.append(category)
    return categories


def taxonomy_label_map_for_labels(labels: List[str], label_to_taxonomy: Dict[str, str]) -> List[dict]:
    pairs = []
    seen = set()
    for label in labels:
        category = label_to_taxonomy.get(label, "")
        key = (label, category)
        if category and key not in seen:
            pairs.append({"label": label, "taxonomy_category": category})
            seen.add(key)
    return pairs


data_type_map = load_mapping(DATA_TYPES_MAP_CSV)
algorithm_map = load_mapping(ALGORITHMS_MAP_CSV)
input_rows = read_jsonl(INPUT_JSONL)

# Existing reviewed standardization stays unchanged.
rows = []
all_data_type_labels_for_taxonomy = []
all_algorithm_labels_for_taxonomy = []
for row in input_rows:
    raw_data_types = collect_data_types(row)
    raw_algorithms = normalize_list(row.get("algorithm_types_raw", []))

    row["data_types_standardized"] = mapped_unique(raw_data_types, data_type_map)
    row["algorithm_types_standardized"] = mapped_unique(raw_algorithms, algorithm_map)

    # Taxonomy columns are based on both raw extracted labels and reviewed labels.
    # This preserves granular extraction while still producing controlled categories.
    row["_data_type_labels_for_taxonomy"] = unique_preserve_order(raw_data_types + row["data_types_standardized"])
    row["_algorithm_labels_for_taxonomy"] = unique_preserve_order(raw_algorithms + row["algorithm_types_standardized"])

    all_data_type_labels_for_taxonomy.extend(row["_data_type_labels_for_taxonomy"])
    all_algorithm_labels_for_taxonomy.extend(row["_algorithm_labels_for_taxonomy"])
    rows.append(row)

# LLM-assisted controlled-category mapping against the predefined config taxonomies.
data_type_taxonomy_map = llm_map_labels_to_taxonomy(
    labels=all_data_type_labels_for_taxonomy,
    taxonomy=DATA_TYPE_TAXONOMY,
    label_type="wearable data type",
    output_cache_csv=DATA_TYPE_TAXONOMY_LLM_MAP_CSV,
)
algorithm_taxonomy_map = llm_map_labels_to_taxonomy(
    labels=all_algorithm_labels_for_taxonomy,
    taxonomy=ALGORITHM_TAXONOMY,
    label_type="algorithm or analytic method",
    output_cache_csv=ALGORITHM_TAXONOMY_LLM_MAP_CSV,
)

for row in rows:
    data_labels = row.pop("_data_type_labels_for_taxonomy", [])
    algorithm_labels = row.pop("_algorithm_labels_for_taxonomy", [])

    row["data_type_taxonomy_categories"] = taxonomy_categories_for_labels(data_labels, data_type_taxonomy_map)
    row["algorithm_taxonomy_categories"] = taxonomy_categories_for_labels(algorithm_labels, algorithm_taxonomy_map)

    row["data_type_taxonomy_label_map"] = taxonomy_label_map_for_labels(data_labels, data_type_taxonomy_map)
    row["algorithm_taxonomy_label_map"] = taxonomy_label_map_for_labels(algorithm_labels, algorithm_taxonomy_map)

write_jsonl(OUTPUT_JSONL, rows)
write_csv(OUTPUT_CSV, rows)
print(f"Wrote final mapped extraction files:\n{OUTPUT_JSONL}\n{OUTPUT_CSV}")
print(f"Wrote LLM-assisted taxonomy mapping review files:\n{DATA_TYPE_TAXONOMY_LLM_MAP_CSV}\n{ALGORITHM_TAXONOMY_LLM_MAP_CSV}")

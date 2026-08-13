from common import OUTPUT_DIR, read_jsonl, write_jsonl, write_csv

INPUT_JSONL = OUTPUT_DIR / "06_final_mapped_extractions.jsonl"
OUTPUT_JSONL = OUTPUT_DIR / "07_algorithm_development_only.jsonl"
OUTPUT_CSV = OUTPUT_DIR / "07_algorithm_development_only.csv"

rows = []
for row in read_jsonl(INPUT_JSONL):
    developed = str(row.get("algorithm_developed", "")).strip().lower()
    if developed == "yes":
        rows.append(row)

write_jsonl(OUTPUT_JSONL, rows)
write_csv(OUTPUT_CSV, rows)
print(f"Wrote {len(rows)} algorithm-development records to {OUTPUT_JSONL} and {OUTPUT_CSV}")

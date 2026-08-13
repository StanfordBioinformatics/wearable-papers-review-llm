import csv
import json
from common import ROOT, OUTPUT_DIR, load_prompt, fixed_criteria_block, call_openai_json, write_jsonl, write_csv

INPUT_CSV = ROOT / "examples" / "pubmed_records_template.csv"
OUTPUT_JSONL = OUTPUT_DIR / "01_title_abstract_screening.jsonl"
OUTPUT_CSV = OUTPUT_DIR / "01_title_abstract_screening.csv"

prompt_template = load_prompt("title_abstract_screening_prompt.txt")
criteria_block = fixed_criteria_block(include_screening_schema=True)

rows = []
with INPUT_CSV.open("r", encoding="utf-8") as f:
    for record in csv.DictReader(f):
        prompt = f"""{prompt_template}

Fixed review criteria and required output schema:
{criteria_block}

PubMed record to screen:
{json.dumps(record, ensure_ascii=False, indent=2)}"""
        result = call_openai_json(prompt)
        result.setdefault("pmid", record.get("pmid", ""))
        result.setdefault("title", record.get("title", ""))
        rows.append(result)

write_jsonl(OUTPUT_JSONL, rows)
write_csv(OUTPUT_CSV, rows)
print(f"Wrote {len(rows)} records to {OUTPUT_JSONL} and {OUTPUT_CSV}")

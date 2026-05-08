"""Optional second-pass review step.
By default, this script uses the same OpenAI call. To use Claude or Gemini as external reviewers,
replace call_openai_json with your preferred provider-specific function while keeping the same prompt.
"""
import json
from common import OUTPUT_DIR, load_prompt, fixed_criteria_block, read_jsonl, call_openai_json, write_jsonl, write_csv

INPUT_JSONL = OUTPUT_DIR / "03_primary_content_extraction.jsonl"
OUTPUT_JSONL = OUTPUT_DIR / "04_reviewer_comments.jsonl"
OUTPUT_CSV = OUTPUT_DIR / "04_reviewer_comments.csv"

prompt_template = load_prompt("reviewer_prompt.txt")
criteria_block = fixed_criteria_block()
rows = []

for extraction in read_jsonl(INPUT_JSONL):
    prompt = f"""{prompt_template}

Fixed review criteria:
{criteria_block}

Primary extraction to review:
{json.dumps(extraction, ensure_ascii=False, indent=2)}"""
    review = call_openai_json(prompt)
    review["PMID"] = extraction.get("PMID") or extraction.get("pmid")
    review["source_pdf"] = extraction.get("source_pdf")
    rows.append(review)

write_jsonl(OUTPUT_JSONL, rows)
write_csv(OUTPUT_CSV, rows)
print(f"Wrote {len(rows)} reviewer records to {OUTPUT_JSONL} and {OUTPUT_CSV}")

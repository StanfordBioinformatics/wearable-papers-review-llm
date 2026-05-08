import json
from common import ROOT, OUTPUT_DIR, load_prompt, fixed_criteria_block, upload_file, call_openai_json, write_jsonl, write_csv, extract_pmid_from_filename

PDF_DIR = ROOT / "papers"
OUTPUT_JSONL = OUTPUT_DIR / "02_full_text_screening.jsonl"
OUTPUT_CSV = OUTPUT_DIR / "02_full_text_screening.csv"

prompt_template = load_prompt("full_text_screening_prompt.txt")
criteria_block = fixed_criteria_block(include_screening_schema=True)
rows = []

for pdf in sorted(PDF_DIR.glob("*.pdf")):
    pmid_hint = extract_pmid_from_filename(pdf.name)
    prompt = f"""{prompt_template}

Filename: {pdf.name}
PMID hint from filename: {pmid_hint}

Fixed review criteria and required output schema:
{criteria_block}"""
    file_id = upload_file(pdf)
    result = call_openai_json(prompt, input_file_id=file_id)
    result.setdefault("pmid", pmid_hint)
    result.setdefault("source_pdf", pdf.name)
    rows.append(result)

write_jsonl(OUTPUT_JSONL, rows)
write_csv(OUTPUT_CSV, rows)
print(f"Wrote {len(rows)} records to {OUTPUT_JSONL} and {OUTPUT_CSV}")

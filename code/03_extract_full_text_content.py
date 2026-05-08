from common import ROOT, OUTPUT_DIR, load_prompt, fixed_criteria_block, upload_file, call_openai_json, write_jsonl, write_csv, extract_pmid_from_filename

PDF_DIR = ROOT / "papers"
OUTPUT_JSONL = OUTPUT_DIR / "03_primary_content_extraction.jsonl"
OUTPUT_CSV = OUTPUT_DIR / "03_primary_content_extraction.csv"
OUTPUT_PROMPT_RECORD = OUTPUT_DIR / "03_content_extraction_prompt_record.txt"

prompt_template = load_prompt("content_extraction_prompt.txt")
criteria_block = fixed_criteria_block(include_content_schema=True)
OUTPUT_PROMPT_RECORD.write_text(prompt_template + "\n\n" + criteria_block, encoding="utf-8")
rows = []

for pdf in sorted(PDF_DIR.glob("*.pdf")):
    pmid_hint = extract_pmid_from_filename(pdf.name)
    prompt = f"""{prompt_template}

Filename: {pdf.name}
PMID hint from filename: {pmid_hint}

Fixed extraction criteria and required output schema:
{criteria_block}"""
    file_id = upload_file(pdf)
    result = call_openai_json(prompt, input_file_id=file_id)
    result.setdefault("PMID", pmid_hint or result.get("pmid"))
    result.setdefault("source_pdf", pdf.name)
    rows.append(result)

write_jsonl(OUTPUT_JSONL, rows)
write_csv(OUTPUT_CSV, rows)
print(f"Wrote {len(rows)} records to {OUTPUT_JSONL} and {OUTPUT_CSV}")
print(f"Saved exact extraction prompt record to {OUTPUT_PROMPT_RECORD}")

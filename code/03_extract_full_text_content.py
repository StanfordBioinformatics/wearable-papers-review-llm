from common import ROOT, OUTPUT_DIR, load_prompt, fixed_criteria_block, upload_file, call_openai_json, write_jsonl, write_csv, extract_pmid_from_filename, canonical_list, load_json

PDF_DIR = ROOT / "papers"
OUTPUT_JSONL = OUTPUT_DIR / "03_primary_content_extraction.jsonl"
OUTPUT_CSV = OUTPUT_DIR / "03_primary_content_extraction.csv"
OUTPUT_PROMPT_RECORD = OUTPUT_DIR / "03_content_extraction_prompt_record.txt"

prompt_template = load_prompt("content_extraction_prompt.txt")
criteria_block = fixed_criteria_block(include_content_schema=True)
OUTPUT_PROMPT_RECORD.write_text(prompt_template + "\n\n" + criteria_block, encoding="utf-8")

devices = load_json("consumer_wearable_devices.json")
domains = load_json("health_domains.json")
data_taxonomy = load_json("data_type_taxonomy.json")
algorithm_taxonomy = load_json("algorithm_taxonomy.json")

rows = []
for pdf in sorted(PDF_DIR.glob("*.pdf")):
    pmid_hint = extract_pmid_from_filename(pdf.name)
    prompt = f"""{prompt_template}

Filename: {pdf.name}
PMID hint from filename: {pmid_hint}

Fixed extraction criteria, controlled vocabularies, and required output schema:
{criteria_block}"""
    file_id = upload_file(pdf)
    result = call_openai_json(prompt, input_file_id=file_id)

    result.setdefault("PMID", pmid_hint or result.get("pmid"))
    result.setdefault("source_pdf", pdf.name)

    result["health_domains"] = canonical_list(result.get("health_domains"), domains)
    result["consumer_wearables_used"] = canonical_list(result.get("consumer_wearables_used"), devices)
    result["data_type_taxonomy_categories"] = canonical_list(
        result.get("data_type_taxonomy_categories"), data_taxonomy
    )
    result["algorithm_taxonomy_categories"] = canonical_list(
        result.get("algorithm_taxonomy_categories"), algorithm_taxonomy
    )
    rows.append(result)

write_jsonl(OUTPUT_JSONL, rows)
write_csv(OUTPUT_CSV, rows)
print(f"Wrote {len(rows)} records to {OUTPUT_JSONL} and {OUTPUT_CSV}")
print(f"Saved exact extraction prompt record to {OUTPUT_PROMPT_RECORD}")

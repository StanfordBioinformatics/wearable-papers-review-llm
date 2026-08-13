"""Required multi-LLM review step.

Despite the historical filename ending in "_optional", this step is REQUIRED to match the
manuscript workflow. Each GPT extraction is independently reviewed by Anthropic Claude and
Google Gemini against the article text. Any disagreement, proposed revision, uncertainty,
invalid controlled label, or reviewer failure is routed to human adjudication.
"""

import json

from common import (
    ROOT,
    OUTPUT_DIR,
    load_prompt,
    fixed_criteria_block,
    read_jsonl,
    write_jsonl,
    write_csv,
    load_json,
    read_pdf_text,
    sha256_text,
    call_anthropic_json,
    call_gemini_json,
    canonical_list,
    get_row_id,
)

INPUT_JSONL = OUTPUT_DIR / "03_primary_content_extraction.jsonl"

CLAUDE_JSONL = OUTPUT_DIR / "04_claude_reviews.jsonl"
CLAUDE_CSV = OUTPUT_DIR / "04_claude_reviews.csv"
GEMINI_JSONL = OUTPUT_DIR / "04_gemini_reviews.jsonl"
GEMINI_CSV = OUTPUT_DIR / "04_gemini_reviews.csv"

SUMMARY_JSONL = OUTPUT_DIR / "04_multi_llm_review_summary.jsonl"
SUMMARY_CSV = OUTPUT_DIR / "04_multi_llm_review_summary.csv"
AUTO_PASSED_JSONL = OUTPUT_DIR / "04_auto_passed_extractions.jsonl"
AUTO_PASSED_CSV = OUTPUT_DIR / "04_auto_passed_extractions.csv"
HUMAN_REPORT_CSV = OUTPUT_DIR / "04_human_review_report.csv"
HUMAN_TEMPLATE_CSV = OUTPUT_DIR / "04_human_adjudication_template.csv"

review_prompt = load_prompt("reviewer_prompt.txt")
criteria_block = fixed_criteria_block(include_review_schema=True)
settings = load_json("model_settings.json")
max_article_chars = int(settings.get("review_max_article_chars", 600000))

devices = load_json("consumer_wearable_devices.json")
domains = load_json("health_domains.json")
data_taxonomy = load_json("data_type_taxonomy.json")
algorithm_taxonomy = load_json("algorithm_taxonomy.json")

FIELD_SPECS = {
    "health_domains": (domains, "proposed_values"),
    "consumer_wearables_used": (devices, "proposed_values"),
    "data_type_taxonomy_categories": (data_taxonomy, "proposed_values"),
    "algorithm_taxonomy_categories": (algorithm_taxonomy, "proposed_values"),
}


def find_pdf(extraction):
    source = str(extraction.get("source_pdf") or "").strip()
    if source:
        path = ROOT / "papers" / source
        if path.exists():
            return path
    pmid = str(extraction.get("PMID") or extraction.get("pmid") or "").strip()
    if pmid:
        matches = sorted((ROOT / "papers").glob(f"{pmid}*.pdf"))
        if matches:
            return matches[0]
    return None


def normalize_reviewer_output(review):
    if not isinstance(review, dict):
        return {}
    if not isinstance(review.get("field_reviews"), dict):
        review["field_reviews"] = {}
    return review


def review_one(provider, extraction, article_text, source_pdf):
    prompt = f"""{review_prompt}

Fixed vocabularies, definitions, and required reviewer output schema:
{criteria_block}

PRIMARY GPT EXTRACTION:
{json.dumps(extraction, ensure_ascii=False, indent=2)}

FULL ARTICLE TEXT:
--- BEGIN ARTICLE TEXT: {source_pdf} ---
{article_text}
--- END ARTICLE TEXT ---
"""
    if provider == "claude":
        return normalize_reviewer_output(call_anthropic_json(prompt))
    if provider == "gemini":
        return normalize_reviewer_output(call_gemini_json(prompt))
    raise ValueError(provider)


def reviewer_field(review, field):
    return ((review or {}).get("field_reviews") or {}).get(field) or {}


def reviewer_values(review, field, primary):
    item = reviewer_field(review, field)
    allowed, key = FIELD_SPECS[field]
    proposed = canonical_list(item.get(key), allowed)
    if str(item.get("status", "")).strip().lower() == "confirmed" and not proposed:
        return canonical_list(primary.get(field), allowed)
    return proposed


def reviewer_algorithm_developed(review, primary):
    item = reviewer_field(review, "algorithm_developed")
    proposed = str(item.get("proposed_value") or "").strip()
    if str(item.get("status", "")).strip().lower() == "confirmed" and not proposed:
        proposed = str(primary.get("algorithm_developed") or "").strip()
    return proposed


def field_needs_human(primary, claude, gemini, field):
    allowed, _ = FIELD_SPECS[field]
    p = canonical_list(primary.get(field), allowed)
    c_item = reviewer_field(claude, field)
    g_item = reviewer_field(gemini, field)
    c_status = str(c_item.get("status", "")).strip().lower()
    g_status = str(g_item.get("status", "")).strip().lower()
    c = reviewer_values(claude, field, primary)
    g = reviewer_values(gemini, field, primary)

    reasons = []
    if c_status != "confirmed":
        reasons.append(f"Claude status={c_item.get('status', '') or 'missing'}")
    if g_status != "confirmed":
        reasons.append(f"Gemini status={g_item.get('status', '') or 'missing'}")
    if set(c) != set(p):
        reasons.append("Claude proposed values differ from GPT")
    if set(g) != set(p):
        reasons.append("Gemini proposed values differ from GPT")
    if set(c) != set(g):
        reasons.append("Claude and Gemini disagree")

    raw_primary = canonical_list(primary.get(field))
    invalid_primary = [x for x in raw_primary if x not in allowed]
    if invalid_primary:
        reasons.append(f"GPT contains invalid controlled labels: {invalid_primary}")

    return bool(reasons), reasons, p, c, g


def algorithm_status_needs_human(primary, claude, gemini):
    p = str(primary.get("algorithm_developed") or "").strip()
    c_item = reviewer_field(claude, "algorithm_developed")
    g_item = reviewer_field(gemini, "algorithm_developed")
    c_status = str(c_item.get("status", "")).strip().lower()
    g_status = str(g_item.get("status", "")).strip().lower()
    c = reviewer_algorithm_developed(claude, primary)
    g = reviewer_algorithm_developed(gemini, primary)

    reasons = []
    if p not in {"Yes", "No", "Not sure"}:
        reasons.append(f"GPT algorithm_developed invalid: {p!r}")
    if c_status != "confirmed":
        reasons.append(f"Claude status={c_item.get('status', '') or 'missing'}")
    if g_status != "confirmed":
        reasons.append(f"Gemini status={g_item.get('status', '') or 'missing'}")
    if c != p:
        reasons.append("Claude proposed algorithm_developed differs from GPT")
    if g != p:
        reasons.append("Gemini proposed algorithm_developed differs from GPT")
    if c != g:
        reasons.append("Claude and Gemini disagree on algorithm_developed")

    return bool(reasons), reasons, p, c, g


primaries = read_jsonl(INPUT_JSONL)
claude_rows, gemini_rows, summary_rows = [], [], []
passed_rows, human_rows, human_template_rows = [], [], []

for i, extraction in enumerate(primaries, start=1):
    row_id = get_row_id(extraction)
    pdf = find_pdf(extraction)
    provider_errors = []
    article_text = ""

    if pdf is None:
        provider_errors.append("Source PDF not found")
        source_pdf = str(extraction.get("source_pdf") or "")
    else:
        source_pdf = pdf.name
        try:
            article_text = read_pdf_text(pdf, max_chars=max_article_chars)
            if not article_text.strip():
                provider_errors.append("PDF text extraction returned empty text")
        except Exception as exc:
            provider_errors.append(f"PDF text extraction failed: {exc}")

    claude, gemini = {}, {}
    if article_text.strip():
        try:
            claude = review_one("claude", extraction, article_text, source_pdf)
        except Exception as exc:
            provider_errors.append(f"Claude review failed: {exc}")
            claude = {
                "review_status": "Uncertain",
                "human_review_required": "Yes",
                "notes": str(exc),
            }

        try:
            gemini = review_one("gemini", extraction, article_text, source_pdf)
        except Exception as exc:
            provider_errors.append(f"Gemini review failed: {exc}")
            gemini = {
                "review_status": "Uncertain",
                "human_review_required": "Yes",
                "notes": str(exc),
            }

    base_meta = {
        "PMID": extraction.get("PMID") or extraction.get("pmid"),
        "source_pdf": source_pdf,
        "article_text_chars": len(article_text),
        "article_text_sha256": sha256_text(article_text) if article_text else "",
    }

    claude_rows.append({**base_meta, **claude})
    gemini_rows.append({**base_meta, **gemini})

    flags, comparison = {}, {}
    all_reasons = list(provider_errors)

    for field in FIELD_SPECS:
        flag, reasons, p, c, g = field_needs_human(extraction, claude, gemini, field)
        flags[field] = flag
        comparison[field] = {"gpt": p, "claude": c, "gemini": g, "reasons": reasons}
        all_reasons.extend([f"{field}: {r}" for r in reasons])

    flag, reasons, p, c, g = algorithm_status_needs_human(extraction, claude, gemini)
    flags["algorithm_developed"] = flag
    comparison["algorithm_developed"] = {"gpt": p, "claude": c, "gemini": g, "reasons": reasons}
    all_reasons.extend([f"algorithm_developed: {r}" for r in reasons])

    if str(claude.get("human_review_required", "")).strip().lower() == "yes":
        all_reasons.append("Claude explicitly requested human review")
    if str(gemini.get("human_review_required", "")).strip().lower() == "yes":
        all_reasons.append("Gemini explicitly requested human review")

    # De-duplicate while preserving order.
    all_reasons = list(dict.fromkeys(all_reasons))
    needs_human = bool(all_reasons)
    disposition = "HUMAN_REVIEW_REQUIRED" if needs_human else "AUTO_PASS"

    summary_rows.append({
        **base_meta,
        "review_disposition": disposition,
        "field_flags": flags,
        "review_comparison": comparison,
        "flag_reasons": all_reasons,
        "claude_review_status": claude.get("review_status"),
        "gemini_review_status": gemini.get("review_status"),
        "claude_notes": claude.get("notes"),
        "gemini_notes": gemini.get("notes"),
    })

    if not needs_human:
        final_row = dict(extraction)
        final_row["multi_llm_review_disposition"] = "AUTO_PASS"
        final_row["claude_review_status"] = claude.get("review_status")
        final_row["gemini_review_status"] = gemini.get("review_status")
        passed_rows.append(final_row)
    else:
        human_rows.append({
            "PMID": base_meta["PMID"],
            "source_pdf": source_pdf,
            "flagged_fields_json": json.dumps([k for k, v in flags.items() if v], ensure_ascii=False),
            "flag_reasons_json": json.dumps(all_reasons, ensure_ascii=False),
            "gpt_health_domains_json": json.dumps(comparison["health_domains"]["gpt"], ensure_ascii=False),
            "claude_health_domains_json": json.dumps(comparison["health_domains"]["claude"], ensure_ascii=False),
            "gemini_health_domains_json": json.dumps(comparison["health_domains"]["gemini"], ensure_ascii=False),
            "gpt_devices_json": json.dumps(comparison["consumer_wearables_used"]["gpt"], ensure_ascii=False),
            "claude_devices_json": json.dumps(comparison["consumer_wearables_used"]["claude"], ensure_ascii=False),
            "gemini_devices_json": json.dumps(comparison["consumer_wearables_used"]["gemini"], ensure_ascii=False),
            "gpt_data_types_json": json.dumps(comparison["data_type_taxonomy_categories"]["gpt"], ensure_ascii=False),
            "claude_data_types_json": json.dumps(comparison["data_type_taxonomy_categories"]["claude"], ensure_ascii=False),
            "gemini_data_types_json": json.dumps(comparison["data_type_taxonomy_categories"]["gemini"], ensure_ascii=False),
            "gpt_algorithm_developed": comparison["algorithm_developed"]["gpt"],
            "claude_algorithm_developed": comparison["algorithm_developed"]["claude"],
            "gemini_algorithm_developed": comparison["algorithm_developed"]["gemini"],
            "gpt_algorithm_categories_json": json.dumps(comparison["algorithm_taxonomy_categories"]["gpt"], ensure_ascii=False),
            "claude_algorithm_categories_json": json.dumps(comparison["algorithm_taxonomy_categories"]["claude"], ensure_ascii=False),
            "gemini_algorithm_categories_json": json.dumps(comparison["algorithm_taxonomy_categories"]["gemini"], ensure_ascii=False),
            "claude_notes": claude.get("notes"),
            "gemini_notes": gemini.get("notes"),
        })

        human_template_rows.append({
            "PMID": base_meta["PMID"],
            "source_pdf": source_pdf,
            "adjudication_status": "",
            "final_health_domains_json": "",
            "final_consumer_wearables_used_json": "",
            "final_data_type_taxonomy_categories_json": "",
            "final_algorithm_developed": "",
            "final_algorithm_taxonomy_categories_json": "",
            "human_notes": "",
        })

    print(f"[{i}/{len(primaries)}] {row_id}: {disposition}")

write_jsonl(CLAUDE_JSONL, claude_rows)
write_csv(CLAUDE_CSV, claude_rows)
write_jsonl(GEMINI_JSONL, gemini_rows)
write_csv(GEMINI_CSV, gemini_rows)
write_jsonl(SUMMARY_JSONL, summary_rows)
write_csv(SUMMARY_CSV, summary_rows)
write_jsonl(AUTO_PASSED_JSONL, passed_rows)
write_csv(AUTO_PASSED_CSV, passed_rows)
write_csv(HUMAN_REPORT_CSV, human_rows)
write_csv(HUMAN_TEMPLATE_CSV, human_template_rows)

print()
print(f"Total primary extractions: {len(primaries)}")
print(f"Auto-passed by GPT + Claude + Gemini: {len(passed_rows)}")
print(f"Flagged for human adjudication: {len(human_rows)}")
print(f"Human-review report: {HUMAN_REPORT_CSV}")
print(f"Human-adjudication template: {HUMAN_TEMPLATE_CSV}")
print("After human review, save the completed template as outputs/04_human_adjudication_completed.csv, then run step 05.")

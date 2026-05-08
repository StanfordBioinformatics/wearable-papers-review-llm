# Workflow overview

## Step 1: Title/abstract screening

`code/01_screen_titles_abstracts.py` screens PubMed records using title and abstract only. The prompt is conservative: it excludes clearly irrelevant records and keeps uncertain records as `Unclear` for full-text review.

## Step 2: Full-text screening

`code/02_screen_full_texts.py` reads full-text PDFs and makes final eligibility decisions using the fixed consumer wearable device list and screening criteria.

## Step 3: Full-text extraction

`code/03_extract_full_text_content.py` extracts structured study-level fields from eligible PDFs. It uses fine-grained field-level instructions modeled after the original extraction script and produces JSONL/CSV outputs.

## Step 4: Optional reviewer pass

`code/04_review_extractions_optional.py` reviews the primary extraction for unsupported or inconsistent health-domain, device, data-type, and algorithm labels. This can be adapted to use Claude or Gemini as independent reviewers.

## Step 5: Taxonomy mapping

`code/05_build_taxonomy_mappings.py` generates review tables for raw wearable data types and raw algorithm labels. A human reviewer can edit the final standard label column.

## Step 6: Apply mappings

`code/06_apply_taxonomy_mappings.py` applies human-adjudicated mappings to generate final standardized data-type and algorithm categories.

## Step 7: Algorithm-development subset

`code/07_filter_algorithm_development_papers.py` keeps papers where `algorithm_developed` is `Yes`, supporting downstream analysis of algorithm-development studies.

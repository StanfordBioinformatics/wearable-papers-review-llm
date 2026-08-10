<img src="WearableReviewLLM.png" width="30%" height="30%">

# LLM-Assisted Consumer Wearable Research Systematic Review Pipeline

This repository contains a plain-Python workflow for two reproducible tasks used in a consumer wearable systematic review:

1. **LLM-assisted screening** of PubMed title/abstract records and full-text PDFs.
2. **LLM-assisted full-text content extraction** of health domains, consumer wearable devices, wearable-derived data types, algorithm-development status, algorithm types, participants, study location, and performance metrics.

The workflow is intentionally simple: run the numbered Python files in `code/`. Prompts are stored in `prompts/`, fixed criteria are stored in `configs/`, and outputs are written to `outputs/`.

## Fixed review criteria

The code uses predefined device and health-domain vocabularies stored in JSON:

- `configs/consumer_wearable_devices.json`
- `configs/health_domains.json`

The current in-scope device categories are Fitbit, Apple Watch, Garmin, Oura, Samsung Galaxy Watch, Withings Watch, WHOOP, Empatica, Polar Watch, Xiaomi Watch, and Huawei Watch.

The current health domains are Physical Activity and Mobility, Cardiovascular, Sleep, Mental Health, Autonomic and Stress Physiology, Infectious Disease Monitoring, Metabolic Health, Neurological Disorders, Women's Health, and Respiratory.

## How to run

> [!IMPORTANT]
> Place PubMed title/abstract records in:  
> `examples/pubmed_records_template.csv`
>
> Place full-text PDFs in a folder named:  
> `papers/`

Then run the numbered scripts from the repository root:

```python
python code/00_check_setup.py
python code/01_screen_titles_abstracts.py
python code/02_screen_full_texts.py
python code/03_extract_full_text_content.py
python code/04_review_extractions_optional.py
python code/05_build_taxonomy_mappings.py
python code/06_apply_taxonomy_mappings.py
python code/07_filter_algorithm_development_papers.py

```

The LLM steps require the OpenAI Python library and an `OPENAI_API_KEY` available to Python. The non-LLM taxonomy mapping scripts only use standard Python libraries.

Step 06 preserves the reviewed standardized-label columns (`data_types_standardized` and `algorithm_types_standardized`) and additionally creates final controlled-taxonomy columns using the predefined config files: `data_type_taxonomy_categories`, `algorithm_taxonomy_categories`, `data_type_taxonomy_label_map`, and `algorithm_taxonomy_label_map`, which are retrieved from multiple LLM-assisted extraction outputs as part of our research inclusion. These columns are carried forward automatically into the Step 07 CSV. The LLM-assisted label-to-taxonomy cache files are also written to `outputs/06_data_type_taxonomy_llm_mapping.csv` and `outputs/06_algorithm_taxonomy_llm_mapping.csv` for transparent review.

## Human-in-the-loop review

The workflow is designed for human review at three points:

1. `01_title_abstract_screening.csv` for title/abstract decisions.
2. `02_full_text_screening.csv` for final eligibility decisions.
3. `05_data_type_mapping_for_review.csv` and `05_algorithm_mapping_for_review.csv` for taxonomy adjudication before applying final mappings.


### Full-text review example

As an example of the human-in-the-loop full-text review process, the `examples/` folder includes the review report for the **903 papers assessed at the full-text stage** of the systematic review. For each paper, the file provides the **Reviewer 1 initial decision**, **Reviewer 2 initial decision**, and the **final consensus decision** following adjudication. This example is provided to illustrate the structure and reporting of the full-text review process and to support transparency and reproducibility of the study-selection workflow.


## Outputs

- JSONL outputs preserve full structured records.
- CSV outputs provide review-friendly tables.
- `03_content_extraction_prompt_record.txt` stores the exact extraction prompt and fixed criteria used for full-text extraction.

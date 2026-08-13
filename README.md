<img src="WearableReviewLLM.png" width="30%" height="30%">

# LLM-Assisted Consumer Wearable Research Systematic Review Pipeline

This repository contains a plain-Python workflow for two reproducible tasks used in a consumer wearable systematic review:

1. **LLM-assisted screening** of PubMed title/abstract records and full-text PDFs.
2. **LLM-assisted full-text content extraction** of health domains, consumer wearable devices, wearable-derived data types, algorithm-development status, algorithm types, participants, study location, and performance metrics.

The workflow is intentionally simple: run the numbered Python files in `code/`. Prompts are stored in `prompts/`, fixed criteria are stored in `configs/`, and outputs are written to `outputs/`.

The repository now locks the manuscript-level categories used in the figures:

- **11 consumer wearable categories**
- **10 health domains**
- **25 wearable data-type categories**
- **12 algorithm taxonomy categories**


## Models

Primary extraction:
- OpenAI `gpt-5.2` by default.

Independent reviewers:
- Google `gemini-2.5-pro`.
- Anthropic defaults to `claude-sonnet-4-6`, a configurable current Claude Sonnet 4-family model ID.
- The config separately records the manuscript-reported reviewer family as **Claude Sonnet 4**.

Override any model via environment variables if an exact historical/current model ID is required.

## API keys

Copy `.env.example` to `.env` and set:

```bash
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GEMINI_API_KEY=...
```

Never commit `.env`.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Inputs

> [!IMPORTANT]
> Place title/abstract records at:
> 
> ```text
> examples/pubmed_records_template.csv
> ```
> 
> Place full-text PDFs at:
> 
> ```text
> papers/
> ```
> 
> PDF filenames should preferably start with PMID, for example:
>
> ```text
> 32069288 - Paper title.pdf
>  ```

## Run order

```bash
python code/00_check_setup.py
python code/01_screen_titles_abstracts.py
python code/02_screen_full_texts.py
python code/03_extract_full_text_content.py
python code/04_review_extractions_optional.py
```
It produces:

- `04_claude_reviews.csv`
- `04_gemini_reviews.csv`
- `04_multi_llm_review_summary.csv`
- `04_auto_passed_extractions.csv`
- `04_human_review_report.csv`
- `04_human_adjudication_template.csv`

A record is auto-passed only when Claude and Gemini both confirm the GPT values for:

1. health domains,
2. consumer wearable devices,
3. wearable data-type taxonomy categories,
4. algorithm-development status, and
5. algorithm taxonomy categories.

Any revision, uncertainty, inter-model disagreement, invalid label, missing PDF text, or reviewer/API failure is routed to human review.

If step 04 flags records:

1. Open `outputs/04_human_review_report.csv`.
2. Review the flagged fields against the full article.
3. Fill `outputs/04_human_adjudication_template.csv`.
4. Mark `adjudication_status` as `Resolved`.
5. For a list field you want to change, enter a JSON array, e.g.:
   `["Sleep", "Cardiovascular"]`
6. Leave a final-field cell blank to retain the primary GPT value after human review.
7. To explicitly set a list field to empty, enter `[]`.
8. Save as:
   `outputs/04_human_adjudication_completed.csv`

Then continue:

```bash
python code/05_build_taxonomy_mappings.py
python code/06_apply_taxonomy_mappings.py
python code/07_filter_algorithm_development_papers.py
```

## Main outputs

All reviewed papers:

```text
outputs/06_final_mapped_extractions.csv
```

Algorithm-development subset:

```text
outputs/07_algorithm_development_only.csv
```

Human-review audit trail:

```text
outputs/04_human_review_report.csv
outputs/04_multi_llm_review_summary.csv
```

## Fixed review criteria

The code uses predefined device and health-domain vocabularies stored in JSON:

- `configs/consumer_wearable_devices.json`
- `configs/health_domains.json`

The current in-scope device categories are Fitbit, Apple Watch, Garmin, Oura, Samsung Galaxy Watch, Withings Watch, WHOOP, Empatica, Polar Watch, Xiaomi Watch, and Huawei Watch.

The current health domains are Physical Activity and Mobility, Cardiovascular, Sleep, Mental Health, Autonomic and Stress Physiology, Infectious Disease Monitoring, Metabolic Health, Neurological Disorders, Women's Health, and Respiratory.


## Human-in-the-loop review

The workflow is designed for human review at three points:

1. `01_title_abstract_screening.csv` for title/abstract decisions.
2. `02_full_text_screening.csv` for final eligibility decisions.
3. `04_human_review_report.csv` for taxonomy adjudication before applying final mappings.


import os
from common import ROOT, CONFIG_DIR, PROMPT_DIR, OUTPUT_DIR

required = [
    CONFIG_DIR / "model_settings.json",
    CONFIG_DIR / "health_domains.json",
    CONFIG_DIR / "consumer_wearable_devices.json",
    CONFIG_DIR / "screening_criteria.json",
    CONFIG_DIR / "screening_output_schema.json",
    CONFIG_DIR / "content_extraction_schema.json",
    PROMPT_DIR / "title_abstract_screening_prompt.txt",
    PROMPT_DIR / "full_text_screening_prompt.txt",
    PROMPT_DIR / "content_extraction_prompt.txt",
    PROMPT_DIR / "reviewer_prompt.txt",
]
missing = [str(path) for path in required if not path.exists()]
print(f"Repository root: {ROOT}")
print(f"Outputs folder: {OUTPUT_DIR}")
if missing:
    raise SystemExit("Missing required files:\n" + "\n".join(missing))
print("Required config and prompt files are present.")
print("OPENAI_API_KEY detected." if os.getenv("OPENAI_API_KEY") else "OPENAI_API_KEY not detected. Set it before running LLM steps.")

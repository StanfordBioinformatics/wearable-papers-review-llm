import os
from common import ROOT, CONFIG_DIR, PROMPT_DIR, OUTPUT_DIR, load_json, load_env

load_env()

required = [
    CONFIG_DIR / "model_settings.json",
    CONFIG_DIR / "health_domains.json",
    CONFIG_DIR / "consumer_wearable_devices.json",
    CONFIG_DIR / "data_type_taxonomy.json",
    CONFIG_DIR / "algorithm_taxonomy.json",
    CONFIG_DIR / "screening_criteria.json",
    CONFIG_DIR / "screening_output_schema.json",
    CONFIG_DIR / "content_extraction_schema.json",
    CONFIG_DIR / "reviewer_output_schema.json",
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

devices = load_json("consumer_wearable_devices.json")
domains = load_json("health_domains.json")
data_types = load_json("data_type_taxonomy.json")
algorithms = load_json("algorithm_taxonomy.json")

assert len(devices) == 11, f"Expected 11 device categories; found {len(devices)}"
assert len(domains) == 10, f"Expected 10 health domains; found {len(domains)}"
assert len(data_types) == 25, f"Expected 25 data-type categories; found {len(data_types)}"
assert len(algorithms) == 12, f"Expected 12 algorithm categories; found {len(algorithms)}"

print("Vocabulary checks passed: 11 devices, 10 health domains, 25 data types, 12 algorithm categories.")

for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"]:
    print(f"{key}: {'detected' if os.getenv(key) else 'NOT detected'}")

settings = load_json("model_settings.json")
print("Primary model:", os.getenv("OPENAI_MODEL") or settings["primary_model"])
print("Anthropic reviewer model:", os.getenv("ANTHROPIC_MODEL") or settings["reviewer_models"]["anthropic"])
print("Gemini reviewer model:", os.getenv("GEMINI_MODEL") or settings["reviewer_models"]["google"])

from pathlib import Path
import csv
import json
import re
import time

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "configs"
PROMPT_DIR = ROOT / "prompts"
OUTPUT_DIR = ROOT / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)


def load_json(name):
    return json.loads((CONFIG_DIR / name).read_text(encoding="utf-8"))


def load_prompt(name):
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def fixed_criteria_block(include_screening_schema=False, include_content_schema=False):
    block = {
        "in_scope_consumer_wearable_device_categories": load_json("consumer_wearable_devices.json"),
        "allowed_health_domains": load_json("health_domains.json"),
        "screening_criteria": load_json("screening_criteria.json"),
    }
    if include_screening_schema:
        block["required_screening_json_output_schema"] = load_json("screening_output_schema.json")
    if include_content_schema:
        block["required_content_extraction_json_output_schema"] = load_json("content_extraction_schema.json")
    return json.dumps(block, ensure_ascii=False, indent=2)


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path):
    rows = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def csv_ready(value):
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys = []
    for row in rows:
        for key in row.keys():
            if key not in keys:
                keys.append(key)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: csv_ready(row.get(k, "")) for k in keys})


def extract_json(text):
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if match:
            return json.loads(match.group(0))
        raise


def get_openai_client():
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise SystemExit("The OpenAI Python library is required for LLM calls. Install it with: pip install openai") from exc
    return OpenAI()


def call_openai_json(prompt, model=None, input_file_id=None, max_retries=None):
    settings = load_json("model_settings.json")
    model = model or settings.get("primary_model", "gpt-5.1")
    max_retries = max_retries or int(settings.get("max_retries", 3))
    sleep_seconds = float(settings.get("sleep_between_calls_sec", 1.5))
    client = get_openai_client()
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            content = []
            if input_file_id:
                content.append({"type": "input_file", "file_id": input_file_id})
            content.append({"type": "input_text", "text": prompt})
            response = client.responses.create(
                model=model,
                input=[{"role": "user", "content": content}],
            )
            return extract_json(response.output_text)
        except Exception as exc:
            last_error = exc
            if attempt < max_retries:
                time.sleep(sleep_seconds * attempt)
    raise RuntimeError(f"LLM call failed after {max_retries} attempts: {last_error}")


def upload_file(path):
    client = get_openai_client()
    with Path(path).open("rb") as f:
        return client.files.create(file=f, purpose="user_data").id


def extract_pmid_from_filename(filename):
    match = re.match(r"^\s*(\d+)\s*[-–_ ]", filename)
    return match.group(1) if match else ""


def normalize_list(value):
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                return [str(v).strip() for v in parsed if str(v).strip()]
        except Exception:
            pass
        return [v.strip() for v in re.split(r";|,", stripped) if v.strip()]
    return []

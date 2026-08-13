from pathlib import Path
import csv
import hashlib
import json
import os
import re
import time

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "configs"
PROMPT_DIR = ROOT / "prompts"
OUTPUT_DIR = ROOT / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_json(name):
    return json.loads((CONFIG_DIR / name).read_text(encoding="utf-8"))


def load_prompt(name):
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def load_env():
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except Exception:
        pass


def fixed_criteria_block(include_screening_schema=False, include_content_schema=False, include_review_schema=False):
    block = {
        "in_scope_consumer_wearable_device_categories": load_json("consumer_wearable_devices.json"),
        "allowed_health_domains": load_json("health_domains.json"),
        "allowed_wearable_data_type_taxonomy": load_json("data_type_taxonomy.json"),
        "allowed_algorithm_taxonomy": load_json("algorithm_taxonomy.json"),
        "screening_criteria": load_json("screening_criteria.json"),
    }
    if include_screening_schema:
        block["required_screening_json_output_schema"] = load_json("screening_output_schema.json")
    if include_content_schema:
        block["required_content_extraction_json_output_schema"] = load_json("content_extraction_schema.json")
    if include_review_schema:
        block["required_reviewer_json_output_schema"] = load_json("reviewer_output_schema.json")
    return json.dumps(block, ensure_ascii=False, indent=2)


def write_jsonl(path, rows):
    path = Path(path)
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
    path = Path(path)
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
    text = (text or "").strip()
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if match:
            return json.loads(match.group(0))
        raise ValueError("Could not parse a JSON object from model output.")


def _retry(fn, max_retries=None):
    settings = load_json("model_settings.json")
    max_retries = int(max_retries or settings.get("max_retries", 3))
    sleep_seconds = float(settings.get("sleep_between_calls_sec", 1.5))
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            return fn()
        except Exception as exc:
            last_error = exc
            if attempt < max_retries:
                time.sleep(sleep_seconds * attempt)
    raise RuntimeError(f"LLM call failed after {max_retries} attempts: {last_error}")


def get_openai_client():
    load_env()
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise SystemExit("Install OpenAI SDK: pip install openai") from exc
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set.")
    return OpenAI()


def call_openai_json(prompt, model=None, input_file_id=None, max_retries=None):
    settings = load_json("model_settings.json")
    model = model or os.getenv("OPENAI_MODEL") or settings.get("primary_model", "gpt-5.2")
    client = get_openai_client()

    def one_call():
        content = []
        if input_file_id:
            content.append({"type": "input_file", "file_id": input_file_id})
        content.append({"type": "input_text", "text": prompt})
        response = client.responses.create(
            model=model,
            input=[{"role": "user", "content": content}],
        )
        return extract_json(response.output_text)

    return _retry(one_call, max_retries=max_retries)


def upload_file(path):
    client = get_openai_client()
    with Path(path).open("rb") as f:
        return client.files.create(file=f, purpose="user_data").id


def get_anthropic_client():
    load_env()
    try:
        import anthropic
    except ImportError as exc:
        raise SystemExit("Install Anthropic SDK: pip install anthropic") from exc
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is not set.")
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def call_anthropic_json(prompt, model=None, max_retries=None):
    settings = load_json("model_settings.json")
    model = model or os.getenv("ANTHROPIC_MODEL") or settings["reviewer_models"]["anthropic"]
    max_tokens = int(settings.get("anthropic_max_output_tokens", 8000))
    client = get_anthropic_client()

    def one_call():
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "\n".join(
            block.text for block in response.content
            if getattr(block, "type", None) == "text" and getattr(block, "text", None)
        )
        return extract_json(text)

    return _retry(one_call, max_retries=max_retries)


def get_gemini_client():
    load_env()
    try:
        from google import genai
    except ImportError as exc:
        raise SystemExit("Install Google Gen AI SDK: pip install google-genai") from exc
    if not os.getenv("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY is not set.")
    return genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def call_gemini_json(prompt, model=None, max_retries=None):
    settings = load_json("model_settings.json")
    model = model or os.getenv("GEMINI_MODEL") or settings["reviewer_models"]["google"]
    max_tokens = int(settings.get("gemini_max_output_tokens", 8192))
    client = get_gemini_client()

    def one_call():
        from google.genai import types
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                max_output_tokens=max_tokens,
            ),
        )
        return extract_json(response.text)

    return _retry(one_call, max_retries=max_retries)


def extract_pmid_from_filename(filename):
    match = re.match(r"^\s*(\d+)\s*[-–_ ]", filename)
    return match.group(1) if match else ""


def normalize_list(value):
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if value is None:
        return []
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
    return [str(value).strip()] if str(value).strip() else []


def unique_preserve_order(values):
    out = []
    for value in values:
        value = str(value).strip()
        if value and value not in out:
            out.append(value)
    return out


def canonical_list(value, allowed=None):
    values = unique_preserve_order(normalize_list(value))
    if allowed is not None:
        values = [v for v in values if v in allowed]
    return values


def read_pdf_text(path, max_chars=None):
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise SystemExit("Install pypdf: pip install pypdf") from exc
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    text = "\n\n".join(pages)
    if max_chars and len(text) > int(max_chars):
        max_chars = int(max_chars)
        half = max_chars // 2
        text = text[:half] + "\n\n...[TRUNCATED FOR REVIEW CONTEXT]...\n\n" + text[-half:]
    return text


def sha256_text(text):
    return hashlib.sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()


def get_row_id(row):
    return str(row.get("PMID") or row.get("pmid") or row.get("source_pdf") or "").strip()


def index_rows(rows):
    return {get_row_id(row): row for row in rows if get_row_id(row)}

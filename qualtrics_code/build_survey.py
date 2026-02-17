#!/usr/bin/env python3
"""
Build/update a Qualtrics survey with a chat UI question.
ENHANCED LOGGING VERSION
"""

from __future__ import annotations

import os
import sys
import logging
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

# =========================
# LOGGING SETUP
# =========================
# Configure logging to show timestamps and levels
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=log_level,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

# =========================
# CONFIGURATION
# =========================

def get_config() -> Dict[str, Any]:
    """Build configuration from environment variables."""
    script_dir = Path(__file__).parent
    
    question_name = os.environ.get("QUESTION_NAME", "chat_ui")
    question_token = normalize_question_token(question_name)
    
    config = {
        "data_center": os.environ.get("QUALTRICS_DATA_CENTER", "yul1"),
        "api_token": os.environ.get("QUALTRICS_API_TOKEN", ""),
        "survey_name": os.environ.get("SURVEY_NAME", "test_1"),
        "question_name": question_name,
        "question_token": question_token,
        "proxy_url": os.environ.get("PROXY_URL", ""),
        "language": "EN",
        "project_category": "CORE",
        "html_path": script_dir / "view.html",
        "css_path": script_dir / "styling.css",
        "js_path": script_dir / "questions.js",
        "data_export_tag": question_name,
    }
    
    # Log config (safe version)
    safe_config = config.copy()
    safe_config["api_token"] = "********" if config["api_token"] else "(missing)"
    safe_config["proxy_url"] = "(set)" if config["proxy_url"] else "(missing)"
    logger.info(f"Loaded Configuration: {json.dumps(safe_config, indent=2, default=str)}")
    
    return config

def normalize_question_token(question_name: str) -> str:
    """Normalize question name for safe DOM IDs and embedded field prefixes."""
    token = re.sub(r"\W+", "_", question_name).strip("_")
    if not token:
        token = "chat_ui"
    return token

def get_shared_fields() -> Dict[str, str]:
    """Build shared embedded data fields (set once per survey, used by all questions)."""
    fields = {
        "proxy_url": os.environ.get("PROXY_URL", ""),
    }
    logger.info(f"Shared fields loaded. Proxy URL present: {bool(fields['proxy_url'])}")
    return fields

def get_question_fields(question_token: str) -> Dict[str, str]:
    """Build per-question embedded data fields with namespaced keys.
    
    Every key is prefixed with '{question_token}_' so multiple questions
    can coexist in a single Embedded Data block without collisions.
    Example: Chat_GPT4_model, Chat_GPT4_prompt, Chat_GPT4_chat_history, etc.
    """
    prefix = f"{question_token}_"
    fields = {
        f"{prefix}model": os.environ.get("MODEL", "gpt-4o"),
        f"{prefix}prompt": os.environ.get("PROMPT", "You are a helpful assistant"),
        f"{prefix}temperature": os.environ.get("TEMPERATURE", "1"),
        f"{prefix}max_tokens": os.environ.get("MAX_TOKENS", "1000"),
        f"{prefix}max_chats": os.environ.get("MAX_CHATS", "99"),
        f"{prefix}delay_per_word": os.environ.get("DELAY_PER_WORD", "0.1"),
        f"{prefix}chat_history": "",
        f"{prefix}chat_question_id": "",
    }
    logger.info(f"Question fields loaded for token '{question_token}' (prefix: '{prefix}').")
    verbose_field_logs = os.environ.get("VERBOSE_FIELD_LOGS", "false").lower() == "true"
    if logger.isEnabledFor(logging.DEBUG) and verbose_field_logs:
        logger.debug(f"Question field details: {json.dumps(fields, indent=2)}")
    return fields

# =========================
# INPUT VALIDATION
# =========================

def validate_inputs(
    config: Dict[str, Any],
    question_data: Dict[str, str],
    shared_data: Dict[str, str],
) -> None:
    """Validate all configurable inputs. Raises ValueError on failure."""
    errors: List[str] = []
    prefix = config["question_token"] + "_"

    # --- String fields must be non-empty ---
    for key, label in (
        ("survey_name", "survey_name"),
        ("question_name", "question_name"),
    ):
        if not config.get(key, "").strip():
            errors.append(f"{label} must be a non-empty string")

    prompt_val = question_data.get(f"{prefix}prompt", "").strip()
    if not prompt_val:
        errors.append("prompt must be a non-empty string")

    model_val = question_data.get(f"{prefix}model", "").strip()
    if not model_val:
        errors.append("model must be a non-empty string")

    proxy_val = shared_data.get("proxy_url", "").strip()
    if not proxy_val:
        errors.append("proxy_url must be a non-empty string")

    # --- Numeric range checks ---

    # temperature: float in [0.0, 2.0]
    temp_raw = question_data.get(f"{prefix}temperature", "")
    try:
        t = float(temp_raw)
        if not (0.0 <= t <= 2.0):
            errors.append(f"temperature must be between 0.0 and 2.0, got {t}")
    except (ValueError, TypeError):
        errors.append(f"temperature must be a valid number, got {temp_raw!r}")

    # max_tokens: positive integer
    mt_raw = question_data.get(f"{prefix}max_tokens", "")
    try:
        mt = int(mt_raw)
        if mt <= 0:
            errors.append(f"max_tokens must be a positive integer, got {mt}")
    except (ValueError, TypeError):
        errors.append(f"max_tokens must be a valid integer, got {mt_raw!r}")

    # max_chats: positive integer
    mc_raw = question_data.get(f"{prefix}max_chats", "")
    try:
        mc = int(mc_raw)
        if mc <= 0:
            errors.append(f"max_chats must be a positive integer, got {mc}")
    except (ValueError, TypeError):
        errors.append(f"max_chats must be a valid integer, got {mc_raw!r}")

    # delay_per_word: non-negative float
    dpw_raw = question_data.get(f"{prefix}delay_per_word", "")
    try:
        dpw = float(dpw_raw)
        if dpw < 0:
            errors.append(f"delay_per_word must be non-negative, got {dpw}")
    except (ValueError, TypeError):
        errors.append(f"delay_per_word must be a valid number, got {dpw_raw!r}")

    # --- Report ---
    if errors:
        for e in errors:
            logger.error(f"Validation error: {e}")
        raise ValueError(
            "Input validation failed:\n  " + "\n  ".join(errors)
        )

    logger.info("All inputs validated successfully.")


# =========================
# EMBEDDED DATA HELPERS
# =========================

def generate_embedded_data_fields(defaults: Dict[str, Any]) -> List[Dict[str, str]]:
    fields = []
    for key, value in sorted(defaults.items()):
        val_str = str(value) if value is not None else ""
        fields.append({"key": key, "value": val_str, "type": "text"})
    return fields

def validate_embedded_field_keys(fields: List[Dict[str, str]]) -> None:
    logger.info("Validating embedded data keys...")
    seen = set()
    for f in fields:
        key = f.get("key", "")
        if not key or " " in key:
            logger.error(f"Invalid key found: '{key}'")
            raise ValueError(f"Invalid embedded field key: {key!r}")
        if key in seen:
            logger.error(f"Duplicate key found: '{key}'")
            raise ValueError(f"Duplicate embedded field key: {key}")
        seen.add(key)
    logger.info("Validation successful.")

# =========================
# FILE HELPERS
# =========================

def read_text_file(path: Path) -> str:
    logger.debug(f"Reading file: {path}")
    if not path.exists():
        logger.critical(f"File not found: {path}")
        raise FileNotFoundError(f"Missing required file: {path.resolve()}")
    return path.read_text(encoding="utf-8")

def build_question_html(html_path: Path, css_path: Path, js_path: Path,
                        question_name: str, question_token: str) -> str:
    """Compile HTML/CSS/JS assets and template the JS with the question name.
    
    Replaces __QN__ with '{question_token}_', __QNSAFE__ with
    '{question_token}', and __QUESTION_NAME__ with
    the literal question name so each question's JS references its own
    namespaced embedded fields (e.g. Chat_GPT4_model, Chat_GPT4_prompt).
    """
    logger.info(
        f"Compiling HTML/CSS/JS assets for question '{question_name}' "
        f"(token '{question_token}')..."
    )
    html = read_text_file(html_path)
    css = read_text_file(css_path)
    js = read_text_file(js_path)
    
    # Template all assets with the question token/name
    html = html.replace("__QN__", f"{question_token}_")
    html = html.replace("__QNSAFE__", question_token)
    css = css.replace("__QNSAFE__", question_token)
    js = js.replace("__QN__", f"{question_token}_")
    js = js.replace("__QNSAFE__", question_token)
    js = js.replace("__QUESTION_NAME__", question_name)
    
    logger.info(
        f"Assets templated: __QN__ -> '{question_token}_', "
        f"__QNSAFE__ -> '{question_token}', "
        f"__QUESTION_NAME__ -> '{question_name}'"
    )
    return f"<style>\n{css}\n</style>\n\n{html}\n\n<script>\n{js}\n</script>\n"

# =========================
# QUALTRICS CLIENT
# =========================

@dataclass(frozen=True)
class QualtricsClient:
    base_url: str
    api_token: str

    def __post_init__(self):
        object.__setattr__(self, "session", requests.Session())
        self.session.headers.update({
            "X-API-TOKEN": self.api_token,
            "Content-Type": "application/json",
        })

    def _req(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{self.base_url}{path}"
        logger.debug(f"API REQUEST: {method} {url}")
        
        try:
            r = self.session.request(method, url, **kwargs)
            # Log response summary
            logger.debug(f"API RESPONSE: {r.status_code} {r.reason}")
            
            r.raise_for_status()
            return r
        except requests.HTTPError as e:
            logger.error(f"HTTP Error: {e}")
            try:
                logger.error(f"Server Response: {r.text}")
            except:
                pass
            raise

    # ---- Survey operations ----

    def list_surveys(self) -> List[Dict[str, Any]]:
        logger.info("Fetching list of surveys...")
        return self._req("GET", "/surveys").json()["result"]["elements"]

    def get_survey_id_by_name(self, name: str) -> Optional[str]:
        logger.info(f"Searching for survey named '{name}'...")
        surveys = self.list_surveys()
        for s in surveys:
            if s.get("name") == name:
                logger.info(f"Match found: {s.get('id')}")
                return s.get("id")
        logger.info("No matching survey found.")
        return None

    def create_survey(self, name: str, language: str, category: str) -> str:
        logger.info(f"Creating new survey '{name}'...")
        payload = {"SurveyName": name, "Language": language, "ProjectCategory": category}
        resp = self._req("POST", "/survey-definitions", json=payload).json()
        new_id = resp["result"]["SurveyID"]
        logger.info(f"Survey created successfully. ID: {new_id}")
        return new_id

    def get_survey_definition(self, survey_id: str) -> Dict[str, Any]:
        return self._req("GET", f"/survey-definitions/{survey_id}").json()["result"]

    # ---- Question operations ----

    def get_question(self, survey_id: str, question_id: str) -> Dict[str, Any]:
        return self._req("GET", f"/survey-definitions/{survey_id}/questions/{question_id}").json()["result"]

    def find_question_id_by_tag(self, survey_id: str, tag: str) -> Optional[str]:
        # Get the survey definition
        definition = self.get_survey_definition(survey_id)
        
        # SAFEGUARD: Extract questions, handling the case where it's a list (empty)
        questions = definition.get("Questions", {})
        if isinstance(questions, list):
            # If Qualtrics returns a list (usually []), treat it as empty dict
            questions = {}

        # Now we can safely iterate
        for qid, q in questions.items():
            if q.get("DataExportTag") == tag:
                return qid
        return None

    def update_question_text(self, survey_id: str, question_id: str, new_text: str) -> None:
        logger.info(f"Updating text for question {question_id}...")
        q = self.get_question(survey_id, question_id)
        q["QuestionText"] = new_text
        self._req("PUT", f"/survey-definitions/{survey_id}/questions/{question_id}", json=q)
        logger.info("Update complete.")

    def create_descriptive_question(self, survey_id: str, question_text: str, tag: str) -> str:
        logger.info(f"Creating new descriptive question with tag '{tag}'...")
        payload = {
            "QuestionText": question_text,
            "DataExportTag": tag,
            "QuestionType": "DB",
            "Selector": "TB",
            "SubSelector": "TX",
            "Configuration": {"QuestionDescriptionOption": "UseText"},
        }
        resp = self._req("POST", f"/survey-definitions/{survey_id}/questions", json=payload).json()
        qid = resp["result"]["QuestionID"]
        logger.info(f"Created question {qid}")
        return qid

    # ---- Flow operations ----

    def get_flow(self, survey_id: str) -> Dict[str, Any]:
        return self._req("GET", f"/survey-definitions/{survey_id}/flow").json()["result"]

    def update_flow(self, survey_id: str, flow: Dict[str, Any]) -> None:
        logger.info("Pushing updated Survey Flow to Qualtrics...")
        self._req("PUT", f"/survey-definitions/{survey_id}/flow", json=flow)
        logger.info("Flow update successful.")

    # ---- Block operations ----

    def get_blocks(self, survey_id: str) -> Dict[str, Any]:
        """Return the Blocks dict from the survey definition."""
        definition = self.get_survey_definition(survey_id)
        blocks = definition.get("Blocks", {})
        if isinstance(blocks, list):
            blocks = {}
        return blocks

    def create_block(self, survey_id: str, description: str) -> str:
        """Create a new Standard block and return its BlockID."""
        logger.info(f"Creating new block '{description}'...")
        payload = {
            "Type": "Standard",
            "Description": description,
        }
        resp = self._req("POST", f"/survey-definitions/{survey_id}/blocks", json=payload).json()
        block_id = resp["result"]["BlockID"]
        logger.info(f"Created block {block_id}")
        return block_id

    def update_block(self, survey_id: str, block_id: str, payload: Dict[str, Any]) -> None:
        """Update an existing block."""
        logger.info(f"Updating block {block_id}...")
        self._req("PUT", f"/survey-definitions/{survey_id}/blocks/{block_id}", json=payload)
        logger.info(f"Block {block_id} updated.")


# =========================
# HIGH-LEVEL WORKFLOW
# =========================

def ensure_survey(client: QualtricsClient, config: Dict[str, Any]) -> str:
    name = config["survey_name"]
    survey_id = client.get_survey_id_by_name(name)
    if survey_id:
        return survey_id
    return client.create_survey(
        name=name,
        language=config["language"],
        category=config["project_category"],
    )

def ensure_chat_question(client: QualtricsClient, survey_id: str, config: Dict[str, Any]) -> tuple:
    """Ensure the chat question exists. Returns (question_id, is_new).

    ``is_new`` is True when the question was just created this run, False
    when it already existed (and was possibly updated in-place).
    """
    tag = config["data_export_tag"]
    question_name = config["question_name"]
    question_token = config["question_token"]
    desired_text = build_question_html(
        html_path=config["html_path"],
        css_path=config["css_path"],
        js_path=config["js_path"],
        question_name=question_name,
        question_token=question_token,
    )

    existing_qid = client.find_question_id_by_tag(survey_id, tag)
    if existing_qid:
        q = client.get_question(survey_id, existing_qid)
        current_text = q.get("QuestionText", "")
        if current_text != desired_text:
            logger.warning(f"Question {existing_qid} content mismatch. Updating...")
            client.update_question_text(survey_id, existing_qid, desired_text)
        else:
            logger.info(f"Question {existing_qid} is up to date.")
        return existing_qid, False

    new_qid = client.create_descriptive_question(survey_id, desired_text, tag)
    return new_qid, True


def ensure_question_block(client: QualtricsClient, survey_id: str,
                          question_qid: str, question_name: str,
                          is_new: bool) -> Optional[str]:
    """
    Place a *newly created* chat question into its own dedicated block.

    This acts as a **landing zone**: when a question is first created it gets
    its own block ("AI Chatbot - {question_name}") near the top of the survey
    flow so the researcher can easily find it.  The researcher is then free to
    move the question into any other block, or keep it where it is.

    On subsequent builds the question already exists, so this function
    **does nothing** -- it will not yank the question back or undo manual
    rearrangements the researcher has made.

    Returns the block ID when a block was created, or None when skipped.
    """
    if not is_new:
        logger.info(
            f"Question '{question_name}' already existed — skipping block "
            f"placement (researcher's arrangement is preserved)."
        )
        return None

    block_description = f"AI Chatbot - {question_name}"

    # --- 1. Create the dedicated block ---
    block_id = client.create_block(survey_id, block_description)

    # --- 2. Move the question from the default block into the new one ---
    all_blocks = client.get_blocks(survey_id)
    for bid, bdata in all_blocks.items():
        if bid == block_id:
            continue
        elements = bdata.get("BlockElements", [])
        original_len = len(elements)
        elements = [
            el for el in elements
            if not (el.get("Type") == "Question" and el.get("QuestionID") == question_qid)
        ]
        if len(elements) != original_len:
            logger.info(f"Removing question {question_qid} from default block {bid}.")
            bdata["BlockElements"] = elements
            client.update_block(survey_id, bid, bdata)

    # Add the question to the dedicated block
    logger.info(f"Adding question {question_qid} to new block {block_id}.")
    target_block = all_blocks.get(block_id, {})
    target_elements = target_block.get("BlockElements", [])
    target_elements.append({"Type": "Question", "QuestionID": question_qid})
    target_block["BlockElements"] = target_elements
    target_block.setdefault("Type", "Standard")
    target_block.setdefault("Description", block_description)
    target_block.setdefault("ID", block_id)
    client.update_block(survey_id, block_id, target_block)

    # --- 3. Add the block to the survey flow ---
    flow = client.get_flow(survey_id)
    flow_elements = flow.get("Flow", [])

    new_flow_element = {
        "Type": "Standard",
        "ID": block_id,
        "FlowID": _next_flow_id(flow_elements),
        "Autofill": [],
    }
    # Insert at position 1 (right after Embedded Data at position 0)
    insert_pos = 1 if flow_elements else 0
    flow_elements.insert(insert_pos, new_flow_element)
    flow["Flow"] = flow_elements
    client.update_flow(survey_id, flow)
    logger.info(f"Added block {block_id} to survey flow at position {insert_pos}.")

    return block_id


def _upsert_embed_block(block: Dict[str, Any], data: Dict[str, str]) -> None:
    """Update or add fields in an existing Embedded Data block."""
    current = block.get("EmbeddedData", [])
    remaining = set(data.keys())
    
    for field_obj in current:
        key = field_obj.get("Field")
        if key in data:
            new_value = str(data[key])
            if field_obj.get("Value") != new_value:
                logger.info(f"Updating '{key}': {field_obj.get('Value')} -> {new_value}")
            field_obj["Value"] = new_value
            field_obj["Type"] = "Custom"
            if "Description" not in field_obj:
                field_obj["Description"] = key
            remaining.discard(key)
    
    # Add any completely new fields
    if remaining:
        logger.info(f"Adding new fields: {remaining}")
        for key in sorted(remaining):
            current.append({
                "Description": key,
                "Field": key,
                "Value": str(data[key]),
                "Type": "Custom"
            })
    
    block["EmbeddedData"] = current

def _next_flow_id(flow_elements: List[Dict]) -> str:
    """Generate a unique FlowID that doesn't collide with existing ones."""
    existing = set()
    for el in flow_elements:
        fid = el.get("FlowID", "")
        if fid.startswith("FL_"):
            try:
                existing.add(int(fid.split("_")[1]))
            except (ValueError, IndexError):
                pass
    next_num = max(existing, default=0) + 1
    return f"FL_{next_num}"

def ensure_embedded_data(client: QualtricsClient, survey_id: str,
                          shared_data: Dict[str, str],
                          question_data: Dict[str, str]) -> None:
    """
    Ensures ALL embedded data fields live in a SINGLE Embedded Data block
    at position 0 of the survey flow.
    
    - Shared fields (e.g. proxy_url) are upserted without a prefix.
    - Per-question fields are already namespaced by the caller
      (e.g. Chat_GPT4_model, Chat_GPT4_prompt).
    - Existing fields from other questions are preserved untouched.
    
    Idempotent: re-running with the same question_name updates values;
    re-running with a new question_name adds new fields alongside existing ones.
    """
    all_data = {**shared_data, **question_data}
    logger.info(f"Ensuring {len(all_data)} embedded data fields in single block at position 0...")
    
    flow = client.get_flow(survey_id)
    flow_elements = flow.get("Flow", [])
    
    # Find existing Embedded Data block anywhere in the top-level flow
    embed_block = None
    embed_index = None
    for i, el in enumerate(flow_elements):
        if el.get("Type") == "EmbeddedData":
            embed_block = el
            embed_index = i
            break
    
    if not embed_block:
        logger.info("Creating new Embedded Data block at position 0.")
        embed_block = {
            "Type": "EmbeddedData",
            "FlowID": _next_flow_id(flow_elements),
            "Description": "Chatbot Parameters",
            "EmbeddedData": [],
        }
        flow_elements.insert(0, embed_block)
    else:
        # Ensure embedded block is always first in flow
        if embed_index is not None and embed_index != 0:
            logger.info(
                f"Moving existing Embedded Data block from index {embed_index} to position 0."
            )
            flow_elements.pop(embed_index)
            flow_elements.insert(0, embed_block)
        else:
            logger.info("Found existing Embedded Data block at position 0.")
    
    # Upsert shared + this question's namespaced fields (preserves all other fields)
    _upsert_embed_block(embed_block, all_data)
    
    flow["Flow"] = flow_elements
    client.update_flow(survey_id, flow)
    logger.info("Embedded data block updated successfully.")
# =========================
# MAIN ENTRY POINT
# =========================

def main() -> int:
    logger.info("==========================================")
    logger.info("       QUALTRICS SURVEY BUILDER           ")
    logger.info("==========================================")

    config = get_config()
    question_name = config["question_name"]
    question_token = config["question_token"]
    shared_data = get_shared_fields()
    question_data = get_question_fields(question_token)

    if not config["api_token"]:
        logger.critical("QUALTRICS_API_TOKEN is missing!")
        return 1

    # Validate all configurable inputs (fail fast on bad values)
    validate_inputs(config, question_data, shared_data)

    # Validate all field keys
    all_fields = generate_embedded_data_fields({**shared_data, **question_data})
    validate_embedded_field_keys(all_fields)

    base_url = f"https://{config['data_center']}.qualtrics.com/API/v3"
    client = QualtricsClient(base_url=base_url, api_token=config["api_token"])

    try:
        logger.info("--- Step 1: Survey Check ---")
        survey_id = ensure_survey(client, config)

        logger.info(f"--- Step 2: Chat UI Question '{question_name}' ---")
        question_qid, is_new = ensure_chat_question(client, survey_id, config)

        logger.info(f"--- Step 2.5: Dedicated Block for '{question_name}' ---")
        ensure_question_block(client, survey_id, question_qid, question_name, is_new)

        logger.info(f"--- Step 3: Embedded Data for '{question_name}' ---")
        ensure_embedded_data(
            client, survey_id,
            shared_data=shared_data,
            question_data=question_data,
        )

        logger.info("==========================================")
        logger.info(f"SUCCESS! Survey '{config['survey_name']}' is ready.")
        logger.info(f"  Question: '{question_name}' (QID: {question_qid})")
        logger.info(f"  Survey ID: {survey_id}")
        logger.info("==========================================")
        return 0

    except Exception as e:
        logger.exception("An unexpected error occurred during execution:")
        return 1

if __name__ == "__main__":
    sys.exit(main())
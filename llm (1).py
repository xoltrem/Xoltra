"""
llm.py — XoltaOS LLM Layer
Cohere-only for now. Multi-provider support will be added later.
Clean JSON parsing, proper error handling, no fake fallbacks.
"""

from dotenv import load_dotenv
import os
import re
import time
import json
import logging
from typing import Optional, Dict

load_dotenv(override=True)

logger = logging.getLogger(__name__)

COHERE_API_KEY = os.getenv("COHERE_API_KEY")


# ═══════════════════════════════════════════════════
# LAZY CLIENT INIT
# ═══════════════════════════════════════════════════

_cohere_client = None

def _init_cohere():
    global _cohere_client
    if not _cohere_client:
        if not COHERE_API_KEY:
            raise RuntimeError("COHERE_API_KEY not set in .env")
        import cohere
        _cohere_client = cohere.Client(COHERE_API_KEY)
    return _cohere_client


# ═══════════════════════════════════════════════════
# MODEL REGISTRY — Cohere only
# ═══════════════════════════════════════════════════

AVAILABLE_MODELS = {
    "cohere-r7b": {
        "provider": "cohere",
        "model": "command-r7b-12-2024",
        "speed": "fast",
        "cost": "low"
    },
    "cohere-r": {
        "provider": "cohere",
        "model": "command-r-08-2024",
        "speed": "medium",
        "cost": "medium"
    },
    "cohere-r-plus": {
        "provider": "cohere",
        "model": "command-r-plus-08-2024",
        "speed": "slow",
        "cost": "high"
    },
    "cohere-a": {
        "provider": "cohere",
        "model": "command-a-03-2025",
        "speed": "medium",
        "cost": "medium"
    },
}

# Single source of truth for defaults
_DEFAULT_ROUTING = {
    "router":              {"model_key": "cohere-r7b", "temperature": 0.0},
    "clarifier":           {"model_key": "cohere-r7b", "temperature": 0.1},
    "extractor":           {"model_key": "cohere-a",   "temperature": 0.2},
    "architect":           {"model_key": "cohere-a",   "temperature": 0.3},
    "critic":              {"model_key": "cohere-r7b", "temperature": 0.1},
    "operator":            {"model_key": "cohere-a",   "temperature": 0.4},
    "auditor":             {"model_key": "cohere-r7b", "temperature": 0.2},
    "validator":           {"model_key": "cohere-r7b", "temperature": 0.0},
    "compiler":            {"model_key": "cohere-a",   "temperature": 0.4},
    "qa":                  {"model_key": "cohere-a",   "temperature": 0.4},
    "knowledge_retriever": {"model_key": "cohere-r7b", "temperature": 0.0},
    "knowledge_linker":    {"model_key": "cohere-a",   "temperature": 0.2},
    "insight_generator":   {"model_key": "cohere-a",   "temperature": 0.3},
    "deduplicator":        {"model_key": "cohere-r7b", "temperature": 0.0},
}

# Live routing — mutated by set_model_for_role
MODEL_ROUTING = {k: dict(v) for k, v in _DEFAULT_ROUTING.items()}

# These agents return prose, not JSON — skip JSON cleaning
PROSE_ROLES = {"compiler", "extractor", "qa", "knowledge_linker", "insight_generator"}


# ═══════════════════════════════════════════════════
# MODEL CONFIGURATION API
# ═══════════════════════════════════════════════════

def set_model_for_role(role: str, model_key: str, temperature: Optional[float] = None):
    if model_key not in AVAILABLE_MODELS:
        raise ValueError(f"Unknown model: {model_key}. Available: {list(AVAILABLE_MODELS.keys())}")
    if role not in MODEL_ROUTING:
        raise ValueError(f"Unknown role: {role}. Available: {list(MODEL_ROUTING.keys())}")
    MODEL_ROUTING[role]["model_key"] = model_key
    if temperature is not None:
        MODEL_ROUTING[role]["temperature"] = temperature
    logger.info(f"[LLM Config] {role} → {model_key} (temp: {MODEL_ROUTING[role]['temperature']})")

def get_all_model_configs() -> Dict:
    return {
        role: {
            **config,
            "provider":   AVAILABLE_MODELS[config["model_key"]]["provider"],
            "model_name": AVAILABLE_MODELS[config["model_key"]]["model"],
            "speed":      AVAILABLE_MODELS[config["model_key"]]["speed"],
            "cost":       AVAILABLE_MODELS[config["model_key"]]["cost"],
        }
        for role, config in MODEL_ROUTING.items()
    }

def reset_model_config():
    global MODEL_ROUTING
    MODEL_ROUTING = {k: dict(v) for k, v in _DEFAULT_ROUTING.items()}
    logger.info("[LLM Config] Reset to defaults")


# ═══════════════════════════════════════════════════
# JSON CLEANING
# ═══════════════════════════════════════════════════

def clean_json(text: str) -> str:
    """
    Strip everything that isn't the JSON object/array.
    Handles: markdown fences, preamble text, trailing commentary.
    """
    text = text.strip()
    text = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"```", "", text).strip()
    match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def safe_json_parse(raw: str) -> dict:
    """
    Parse JSON with helpful error. Never returns a fake fallback.
    Raises ValueError if parsing fails so the caller can handle it.
    """
    cleaned = clean_json(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"JSON parse failed: {e}\nRaw (first 300 chars): {raw[:300]}"
        ) from e


# ═══════════════════════════════════════════════════
# UNIVERSAL LLM CALLER
# ═══════════════════════════════════════════════════

def call_llm(role: str, prompt: str, retries: int = 2) -> str:
    """
    Route prompt to Cohere and return raw response.
    Raises RuntimeError if all retries fail — never returns fake data.
    """
    if role not in MODEL_ROUTING:
        raise ValueError(f"Unknown role: {role}")

    config      = MODEL_ROUTING[role]
    model_key   = config["model_key"]
    model_info  = AVAILABLE_MODELS[model_key]
    model_name  = model_info["model"]
    temperature = config["temperature"]

    last_error = None
    for attempt in range(retries + 1):
        try:
            result = _call_cohere(model_name, prompt, temperature)

            if role not in PROSE_ROLES:
                result = clean_json(result)

            logger.debug(f"[{role.upper()}] cohere/{model_key} OK — {len(result)} chars")
            return result

        except Exception as e:
            last_error = e
            logger.warning(f"[{role.upper()}] Attempt {attempt + 1}/{retries + 1} failed: {e}")
            if attempt < retries:
                time.sleep(2 ** attempt)  # exponential backoff: 1s, 2s

    raise RuntimeError(f"[{role.upper()}] All {retries + 1} attempts failed. Last error: {last_error}")


# ═══════════════════════════════════════════════════
# COHERE IMPLEMENTATION
# ═══════════════════════════════════════════════════

def _call_cohere(model: str, prompt: str, temperature: float) -> str:
    client = _init_cohere()
    response = client.chat(
        model=model,
        message=prompt,
        temperature=temperature,
        max_tokens=3000
    )
    return response.text.strip()


# ═══════════════════════════════════════════════════
# EMBEDDINGS — Cohere only
# ═══════════════════════════════════════════════════

def generate_embedding(text: str) -> list:
    """Generate document embedding. Returns [] on failure."""
    try:
        client = _init_cohere()
        response = client.embed(
            texts=[text],
            model="embed-english-v3.0",
            input_type="search_document"
        )
        return response.embeddings[0]
    except Exception as e:
        logger.warning(f"[EMBEDDING] Failed: {e}")
        return []

def generate_query_embedding(text: str) -> list:
    """Generate query embedding. Returns [] on failure."""
    try:
        client = _init_cohere()
        response = client.embed(
            texts=[text],
            model="embed-english-v3.0",
            input_type="search_query"
        )
        return response.embeddings[0]
    except Exception as e:
        logger.warning(f"[QUERY_EMBEDDING] Failed: {e}")
        return []


# ═══════════════════════════════════════════════════
# AGENT WRAPPERS — backward-compatible named calls
# ═══════════════════════════════════════════════════

def call_router(prompt):               return call_llm("router", prompt)
def call_clarifier(prompt):            return call_llm("clarifier", prompt)
def call_extractor(prompt):            return call_llm("extractor", prompt)
def call_architect(prompt):            return call_llm("architect", prompt)
def call_critic(prompt):               return call_llm("critic", prompt)
def call_operator(prompt):             return call_llm("operator", prompt)
def call_auditor(prompt):              return call_llm("auditor", prompt)
def call_validator(prompt):            return call_llm("validator", prompt)
def call_compiler(prompt):             return call_llm("compiler", prompt)
def call_qa(prompt):                   return call_llm("qa", prompt)
def call_knowledge_retriever(prompt):  return call_llm("knowledge_retriever", prompt)
def call_knowledge_linker(prompt):     return call_llm("knowledge_linker", prompt)
def call_insight_generator(prompt):    return call_llm("insight_generator", prompt)
def call_deduplicator(prompt):         return call_llm("deduplicator", prompt)


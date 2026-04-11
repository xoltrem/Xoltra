"""
llm.py — XoltaOS LLM Layer
Cohere-only for now. Multi-provider support will be added later.
Clean JSON parsing, proper error handling, no fake fallbacks.
Supports role_preamble — injected as Cohere system-level preamble.
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
# COHERE IMPLEMENTATION
# ═══════════════════════════════════════════════════

def _call_cohere(prompt: str, model: str, temperature: float,
                 preamble: Optional[str] = None) -> str:
    """
    Internal Cohere caller.
    preamble is injected as the system-level persona instruction.
    Cohere's preamble param is the canonical system prompt equivalent.
    """
    client = _init_cohere()

    kwargs = {
        "model":       model,
        "message":     prompt,
        "temperature": temperature,
        "max_tokens":  3000,
    }
    if preamble:
        kwargs["preamble"] = preamble

    response = client.chat(**kwargs)
    return response.text.strip()


# ═══════════════════════════════════════════════════
# UNIVERSAL LLM CALLER
# ═══════════════════════════════════════════════════

def call_llm(role: str, prompt: str, retries: int = 2,
             role_preamble: Optional[str] = None) -> str:
    """
    Universal LLM caller. role = agent role key (e.g. "architect").
    role_preamble = optional persona string from roles.py, injected at
    the Cohere preamble level so it conditions all agent output in a session.

    JSON roles: response is cleaned via clean_json().
    PROSE_ROLES: response returned as-is.
    Raises RuntimeError if all retries exhausted.
    """
    config     = MODEL_ROUTING.get(role, MODEL_ROUTING["architect"])
    model_key  = config["model_key"]
    temp       = config["temperature"]
    model_name = AVAILABLE_MODELS[model_key]["model"]

    last_error = None
    for attempt in range(retries + 1):
        try:
            raw = _call_cohere(prompt, model_name, temp, preamble=role_preamble)
            if role not in PROSE_ROLES:
                return clean_json(raw)
            return raw
        except Exception as e:
            last_error = e
            logger.warning(f"[{role.upper()}] Attempt {attempt + 1}/{retries + 1} failed: {e}")
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))

    raise RuntimeError(
        f"call_llm failed for role '{role}' after {retries + 1} attempts: {last_error}"
    )


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
# AGENT WRAPPERS — all gain role_preamble param
# ═══════════════════════════════════════════════════

def call_router(prompt: str, role_preamble: Optional[str] = None) -> str:
    return call_llm("router", prompt, role_preamble=role_preamble)

def call_clarifier(prompt: str, role_preamble: Optional[str] = None) -> str:
    return call_llm("clarifier", prompt, role_preamble=role_preamble)

def call_extractor(prompt: str, role_preamble: Optional[str] = None) -> str:
    return call_llm("extractor", prompt, role_preamble=role_preamble)

def call_architect(prompt: str, role_preamble: Optional[str] = None) -> str:
    return call_llm("architect", prompt, role_preamble=role_preamble)

def call_critic(prompt: str, role_preamble: Optional[str] = None) -> str:
    return call_llm("critic", prompt, role_preamble=role_preamble)

def call_operator(prompt: str, role_preamble: Optional[str] = None) -> str:
    return call_llm("operator", prompt, role_preamble=role_preamble)

def call_auditor(prompt: str, role_preamble: Optional[str] = None) -> str:
    return call_llm("auditor", prompt, role_preamble=role_preamble)

def call_validator(prompt: str, role_preamble: Optional[str] = None) -> str:
    return call_llm("validator", prompt, role_preamble=role_preamble)

def call_compiler(prompt: str, role_preamble: Optional[str] = None) -> str:
    return call_llm("compiler", prompt, role_preamble=role_preamble)

def call_qa(prompt: str, role_preamble: Optional[str] = None) -> str:
    return call_llm("qa", prompt, role_preamble=role_preamble)

def call_knowledge_retriever(prompt: str, role_preamble: Optional[str] = None) -> str:
    return call_llm("knowledge_retriever", prompt, role_preamble=role_preamble)

def call_knowledge_linker(prompt: str, role_preamble: Optional[str] = None) -> str:
    return call_llm("knowledge_linker", prompt, role_preamble=role_preamble)

def call_insight_generator(prompt: str, role_preamble: Optional[str] = None) -> str:
    return call_llm("insight_generator", prompt, role_preamble=role_preamble)

def call_deduplicator(prompt: str, role_preamble: Optional[str] = None) -> str:
    return call_llm("deduplicator", prompt, role_preamble=role_preamble)

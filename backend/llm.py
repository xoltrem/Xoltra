"""
llm.py — Xoltra LLM Layer
Cohere-only for now. Multi-provider support will be added later.
Clean JSON parsing, proper error handling, no fake fallbacks.
Supports role_preamble — injected as Cohere system-level preamble.

Tier system (auto-selected by Router):
  ⚡ Fast     (simple)  — Router → QA
  ⚖ Standard (medium)  — Router → Clarifier → Architect → Critic → Validator → Compiler
  🧠 Deep     (complex) — All 14 agents, best models
"""

from dotenv import load_dotenv
import os
import re
import time
import json
import logging
from typing import Optional, Dict, Set

load_dotenv(override=True)

logger = logging.getLogger(__name__)

from memory_router import memory_router

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
# MODEL REGISTRY
# ═══════════════════════════════════════════════════

AVAILABLE_MODELS = {
    "cohere-r7b": {
        "provider": "cohere",
        "model":    "command-r7b-12-2024",
        "speed":    "fast",
        "cost":     "low",
        "tier":     1,
    },
    "cohere-r": {
        "provider": "cohere",
        "model":    "command-r-08-2024",
        "speed":    "medium",
        "cost":     "medium",
        "tier":     2,
    },
    "cohere-a": {
        "provider": "cohere",
        "model":    "command-a-03-2025",
        "speed":    "medium",
        "cost":     "medium",
        "tier":     3,
    },
    "cohere-r-plus": {
        "provider": "cohere",
        "model":    "command-r-plus-08-2024",
        "speed":    "slow",
        "cost":     "high",
        "tier":     4,
    },
}


# ═══════════════════════════════════════════════════
# TIER DEFINITIONS
#
# Analogy: think of this like Gemini's Fast vs Thinking.
# ⚡ Fast     = quick answer, minimal agents, cheapest model
# ⚖ Standard = balanced, core agents, mid-tier models
# 🧠 Deep     = full power, all 14 agents, best models
# ═══════════════════════════════════════════════════

TIERS = {
    "simple": {
        "label":        "⚡ Fast",
        "agents":       {"router", "qa"},
        "light_model":  "cohere-r7b",
        "heavy_model":  "cohere-r7b",
    },
    "medium": {
        "label":        "⚖ Standard",
        "agents":       {
            "router", "clarifier", "architect",
            "critic", "validator", "compiler"
        },
        "light_model":  "cohere-r7b",
        "heavy_model":  "cohere-a",
    },
    "complex": {
        "label":        "🧠 Deep",
        "agents":       {
            "router", "clarifier", "extractor",
            "architect", "critic", "operator",
            "auditor", "validator", "compiler", "qa",
            "knowledge_retriever", "knowledge_linker",
            "insight_generator", "deduplicator"
        },
        "light_model":  "cohere-r",
        "heavy_model":  "cohere-r-plus",
    },
}

# Light agents = fast decisions (routing, validation, deduplication)
# Heavy agents = deep generation (architecture, compilation, insight)
_LIGHT_AGENTS = {
    "router", "clarifier", "critic", "auditor",
    "validator", "deduplicator", "knowledge_retriever"
}
_HEAVY_AGENTS = {
    "architect", "operator", "compiler", "extractor",
    "qa", "knowledge_linker", "insight_generator"
}

# Current active tier — set by apply_tier()
_active_tier: str = "medium"


# ═══════════════════════════════════════════════════
# DEFAULT ROUTING (medium tier baseline)
# ═══════════════════════════════════════════════════

_AGENT_TEMPERATURES = {
    "router":              0.0,
    "clarifier":           0.1,
    "extractor":           0.2,
    "architect":           0.3,
    "critic":              0.1,
    "operator":            0.4,
    "auditor":             0.2,
    "validator":           0.0,
    "compiler":            0.4,
    "qa":                  0.4,
    "knowledge_retriever": 0.0,
    "knowledge_linker":    0.2,
    "insight_generator":   0.3,
    "deduplicator":        0.0,
}

_DEFAULT_ROUTING: Dict[str, Dict] = {
    role: {
        "model_key":   (
            TIERS["medium"]["light_model"]
            if role in _LIGHT_AGENTS
            else TIERS["medium"]["heavy_model"]
        ),
        "temperature": temp,
    }
    for role, temp in _AGENT_TEMPERATURES.items()
}

MODEL_ROUTING: Dict[str, Dict] = {k: dict(v) for k, v in _DEFAULT_ROUTING.items()}

PROSE_ROLES = {"compiler", "extractor", "qa", "knowledge_linker", "insight_generator"}


# ═══════════════════════════════════════════════════
# TIER API — called by pipeline after Router runs
# ═══════════════════════════════════════════════════

def apply_tier(complexity: str):
    """
    Called by the pipeline immediately after Router classifies input.
    Updates MODEL_ROUTING so every agent uses the right model for this tier.
    complexity: "simple" | "medium" | "complex"
    """
    global _active_tier

    if complexity not in TIERS:
        logger.warning(f"[LLM] Unknown complexity '{complexity}' — defaulting to medium")
        complexity = "medium"

    _active_tier = complexity
    tier = TIERS[complexity]

    for role in MODEL_ROUTING:
        model_key = tier["light_model"] if role in _LIGHT_AGENTS else tier["heavy_model"]
        MODEL_ROUTING[role]["model_key"] = model_key

    logger.info(
        f"[LLM] Tier applied: {tier['label']} | "
        f"Agents: {len(tier['agents'])} | "
        f"Models: light={tier['light_model']}, heavy={tier['heavy_model']}"
    )


def get_active_tier() -> dict:
    """Returns the current tier info — useful for frontend display."""
    tier = TIERS.get(_active_tier, TIERS["medium"])
    return {
        "complexity":   _active_tier,
        "label":        tier["label"],
        "agent_count":  len(tier["agents"]),
        "agents":       sorted(tier["agents"]),
        "light_model":  tier["light_model"],
        "heavy_model":  tier["heavy_model"],
    }


def get_active_agents() -> Set[str]:
    """Returns the set of agents that should run for the current tier."""
    return TIERS.get(_active_tier, TIERS["medium"])["agents"]


def is_agent_active(agent_name: str) -> bool:
    """Check if a specific agent should run in the current tier."""
    return agent_name in get_active_agents()


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
    logger.info(f"[LLM Config] {role} → {model_key}")


def get_all_model_configs() -> Dict:
    return {
        role: {
            **config,
            "provider":   AVAILABLE_MODELS[config["model_key"]]["provider"],
            "model_name": AVAILABLE_MODELS[config["model_key"]]["model"],
            "speed":      AVAILABLE_MODELS[config["model_key"]]["speed"],
            "cost":       AVAILABLE_MODELS[config["model_key"]]["cost"],
            "tier":       AVAILABLE_MODELS[config["model_key"]]["tier"],
            "active":     is_agent_active(role),
        }
        for role, config in MODEL_ROUTING.items()
    }


def reset_model_config():
    global MODEL_ROUTING, _active_tier
    MODEL_ROUTING  = {k: dict(v) for k, v in _DEFAULT_ROUTING.items()}
    _active_tier   = "medium"
    logger.info("[LLM Config] Reset to defaults (medium tier)")


# ═══════════════════════════════════════════════════
# JSON CLEANING
# ═══════════════════════════════════════════════════

def clean_json(text: str) -> str:
    text = text.strip()
    text = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"```", "", text).strip()
    match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def safe_json_parse(raw: str) -> dict:
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

import contextvars

_usage_user_id      = contextvars.ContextVar("usage_user_id", default=None)
_usage_execution_id = contextvars.ContextVar("usage_execution_id", default=None)


def set_usage_context(user_id: Optional[str] = None, execution_id: Optional[str] = None) -> None:
    """
    Call at the top of any request-driven entry point that will make LLM
    calls. Every call_llm() invocation on this thread/async-task afterward
    gets its token usage attributed to (user_id, execution_id) automatically
    — no need to thread user_id through every agent function signature.
    """
    if user_id is not None:
        _usage_user_id.set(user_id)
    if execution_id is not None:
        _usage_execution_id.set(execution_id)


def clear_usage_context() -> None:
    _usage_user_id.set(None)
    _usage_execution_id.set(None)


def _record_usage(role: str, model_name: str, usage_sink: dict) -> None:
    tokens = int(usage_sink.get("input_tokens", 0)) + int(usage_sink.get("output_tokens", 0))
    user_id = _usage_user_id.get()
    if not user_id or tokens <= 0:
        return
    try:
        import subscription_manager as sm  # lazy: avoid import-order coupling
        sm.deduct_usage(
            user_id, tokens, model_name=model_name,
            agent_name=role, execution_id=_usage_execution_id.get(),
        )
    except Exception as e:
        logger.warning(f"[LLM] usage recording failed for role={role}: {e}")


def _call_cohere(prompt: str, model: str, temperature: float,
                 preamble: Optional[str] = None, usage_sink: Optional[dict] = None) -> str:
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

    if usage_sink is not None:
        try:
            billed = getattr(response.meta, "billed_units", None)
            usage_sink["input_tokens"]  = int(getattr(billed, "input_tokens", 0) or 0)
            usage_sink["output_tokens"] = int(getattr(billed, "output_tokens", 0) or 0)
        except Exception:
            pass  # usage tracking is best-effort, never blocks the actual response

    return response.text.strip()


# ═══════════════════════════════════════════════════
# UNIVERSAL LLM CALLER
# ═══════════════════════════════════════════════════

def call_llm(role: str, prompt: str, retries: int = 2,
             role_preamble: Optional[str] = None) -> str:
    config     = MODEL_ROUTING.get(role, MODEL_ROUTING["architect"])
    model_key  = config["model_key"]
    temp       = config["temperature"]
    model_name = AVAILABLE_MODELS[model_key]["model"]

    last_error = None
    for attempt in range(retries + 1):
        try:
            usage_sink = {}
            raw = _call_cohere(prompt, model_name, temp, preamble=role_preamble, usage_sink=usage_sink)
            _record_usage(role, model_name, usage_sink)
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
# EMBEDDINGS
# ═══════════════════════════════════════════════════

def generate_embedding(text: str) -> list:
    try:
        client   = _init_cohere()
        response = client.embed(
            texts=[text], model="embed-english-v3.0", input_type="search_document"
        )
        return response.embeddings[0]
    except Exception as e:
        logger.warning(f"[EMBEDDING] Failed: {e}")
        return []


def generate_query_embedding(text: str) -> list:
    try:
        client   = _init_cohere()
        response = client.embed(
            texts=[text], model="embed-english-v3.0", input_type="search_query"
        )
        return response.embeddings[0]
    except Exception as e:
        logger.warning(f"[QUERY_EMBEDDING] Failed: {e}")
        return []


# ═══════════════════════════════════════════════════
# AGENT WRAPPERS — 14 agents
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


# ═══════════════════════════════════════════════════
# PIPELINE ORCHESTRATION  (MemoryRouter-aware)
# Agents imported inside functions to avoid circular
# imports (agents.py imports from llm.py).
# ═══════════════════════════════════════════════════

def run_pipeline(thread_id: str, user_input: str,
                 role_preamble: Optional[str] = None) -> dict:
    """
    Main entry point. Call this when the user submits a new goal.

    Returns one of:
      { "status": "WAITING_FOR_USER", "questions": [...], "thread_id": ... }
        → show questions to the user, then call resume_pipeline() with answers

      { "status": "COMPLETE", "output": "...", "tier": {...}, "thread_id": ... }
        → pipeline finished, render output

      { "status": "ERROR", "error": "...", "thread_id": ... }
    """
    from agents import RouterAgent, ClarifierAgent, QAAgent  # local to avoid circular

    # User may be returning to an already-paused session
    existing = memory_router.resume_session(thread_id)
    if existing and existing.get("status") == "WAITING_FOR_USER":
        return {
            "status":     "WAITING_FOR_USER",
            "stage":      existing.get("stage"),
            "questions":  existing.get("clarification_questions", []),
            "thread_id":  thread_id,
        }

    # ── Stage 1: Route ──
    memory_router.save_temporary_session(thread_id, {
        "status":       "RUNNING",
        "stage":        "routing",
        "goal":         user_input,
        "role_preamble": role_preamble,
    })

    try:
        route = RouterAgent().run(user_input, role_preamble=role_preamble)
    except Exception as exc:
        logger.error("[Pipeline] Router failed for thread=%s: %s", thread_id, exc)
        return {"status": "ERROR", "error": str(exc), "thread_id": thread_id}

    complexity          = route.get("complexity", "medium")
    mode                = route.get("mode", "default")
    pipeline_depth      = route.get("pipeline_depth", "standard")
    needs_clarification = route.get("needs_clarification", False)

    apply_tier(complexity)

    # ── Simple path: Router → QA only ──
    if complexity == "simple":
        try:
            output = QAAgent().run(
                user_input, complexity=complexity,
                mode=mode, role_preamble=role_preamble,
            )
        except Exception as exc:
            return {"status": "ERROR", "error": str(exc), "thread_id": thread_id}

        memory_router.complete_session(thread_id)
        return {
            "status":    "COMPLETE",
            "output":    output,
            "tier":      get_active_tier(),
            "mode":      mode,
            "thread_id": thread_id,
        }

    # ── Stage 2: Clarify if needed ──
    if needs_clarification:
        try:
            clarifier_result = ClarifierAgent().run(user_input, role_preamble=role_preamble)
            questions        = clarifier_result.get("questions", [])
        except Exception as exc:
            return {"status": "ERROR", "error": str(exc), "thread_id": thread_id}

        memory_router.save_temporary_session(thread_id, {
            "status":                  "WAITING_FOR_USER",
            "stage":                   "clarifying",
            "goal":                    user_input,
            "mode":                    mode,
            "complexity":              complexity,
            "pipeline_depth":          pipeline_depth,
            "role_preamble":           role_preamble,
            "clarification_questions": questions,
        })
        # ↑ MemoryRouter auto-pushes to Redis because status == WAITING_FOR_USER

        return {
            "status":    "WAITING_FOR_USER",
            "stage":     "clarifying",
            "questions": questions,
            "thread_id": thread_id,
        }

    # ── No clarification needed — go straight to build ──
    return _run_build_pipeline(
        thread_id=thread_id,
        goal=user_input,
        mode=mode,
        complexity=complexity,
        role_preamble=role_preamble,
        context_nodes=None,
    )


def resume_pipeline(thread_id: str, clarification_answers: dict,
                    role_preamble: Optional[str] = None) -> dict:
    """
    Called when user submits answers to clarification questions.
    Transparently continues from the saved state — no restart needed.

    clarification_answers: { "q1": "answer", "q2": "answer", ... }
    """
    state = memory_router.resume_session(thread_id)

    if not state:
        return {
            "status": "ERROR",
            "error":  "Session expired or not found. Please start again.",
            "thread_id": thread_id,
        }
    if state.get("status") != "WAITING_FOR_USER":
        return {
            "status": "ERROR",
            "error":  f"Unexpected session state: {state.get('status')}",
            "thread_id": thread_id,
        }

    # Enrich the original goal with the user's answers
    goal         = state["goal"]
    answers_text = "\n".join(f"- {k}: {v}" for k, v in clarification_answers.items())
    enriched_goal = f"{goal}\n\nAdditional context from user:\n{answers_text}"

    # Persist answers, mark as RUNNING again
    state.update({
        "status":                 "RUNNING",
        "stage":                  "building",
        "clarification_answers":  clarification_answers,
    })
    memory_router.save_temporary_session(thread_id, state)

    apply_tier(state.get("complexity", "medium"))

    return _run_build_pipeline(
        thread_id=thread_id,
        goal=enriched_goal,
        mode=state.get("mode", "default"),
        complexity=state.get("complexity", "medium"),
        role_preamble=state.get("role_preamble") or role_preamble,
        context_nodes=state.get("context_nodes"),
    )


def _run_build_pipeline(thread_id: str, goal: str, mode: str,
                        complexity: str, role_preamble: Optional[str],
                        context_nodes: Optional[list]) -> dict:
    """
    Internal: Architect → Critic/Operator loop → Validator → Compiler.
    Saves stage checkpoints via MemoryRouter so restarts can recover.
    """
    from agents import (  # local to avoid circular
        ArchitectAgent, CriticAgent, OperatorAgent,
        ValidatorAgent, CompilerAgent,
    )

    MAX_CRITIC_LOOPS = 2

    def _checkpoint(stage: str, extra: Optional[dict] = None):
        memory_router.save_temporary_session(thread_id, {
            "status":       "RUNNING",
            "stage":        stage,
            "goal":         goal,
            "mode":         mode,
            "complexity":   complexity,
            "role_preamble": role_preamble,
            **(extra or {}),
        })

    try:
        # ── Architect ──
        _checkpoint("architecting")
        blueprint = ArchitectAgent().run(
            goal, context_nodes=context_nodes, role_preamble=role_preamble,
        )

        # ── Critic → Operator loop ──
        for loop in range(MAX_CRITIC_LOOPS):
            _checkpoint(f"reviewing_pass_{loop + 1}", {"blueprint": blueprint})
            critique = CriticAgent().run(
                blueprint, original_goal=goal, role_preamble=role_preamble,
            )
            if critique.get("status") == "pass":
                break
            issues = critique.get("issues", [])
            if issues:
                _checkpoint(f"fixing_pass_{loop + 1}", {"blueprint": blueprint})
                blueprint = OperatorAgent().run(
                    blueprint, issues=issues,
                    original_goal=goal, role_preamble=role_preamble,
                )

        # ── Validator ──
        _checkpoint("validating", {"blueprint": blueprint})
        validation = ValidatorAgent().run(blueprint, role_preamble=role_preamble)
        if validation.get("status") == "fail":
            logger.warning(
                "[Pipeline] Validator fail thread=%s: %s",
                thread_id, validation.get("reason"),
            )

        # ── Compiler ──
        _checkpoint("compiling", {"blueprint": blueprint})
        output = CompilerAgent().run(
            blueprint, original_goal=goal,
            mode=mode, context_nodes=context_nodes,
            role_preamble=role_preamble,
        )

    except Exception as exc:
        logger.error("[Pipeline] Build failed thread=%s stage=%s: %s",
                     thread_id, memory_router.get_status(thread_id), exc)
        memory_router.complete_session(thread_id)
        return {"status": "ERROR", "error": str(exc), "thread_id": thread_id}

    memory_router.complete_session(thread_id)   # evict from L1 + Redis

    return {
        "status":    "COMPLETE",
        "output":    output,
        "tier":      get_active_tier(),
        "mode":      mode,
        "thread_id": thread_id,
    }

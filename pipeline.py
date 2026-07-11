"""
pipeline.py — XoltaOS Pipeline Orchestrator

Tier system (auto-selected by Router):
  ⚡ Fast     (simple)  → Router → QA
  ⚖ Standard (medium)  → Router → Clarifier → Architect → Critic → Validator → Compiler
  🧠 Deep     (complex) → All 14 agents

Router runs first, calls apply_tier(complexity), then the pipeline
checks is_agent_active() before running each agent — inactive agents
are skipped silently. This means adding a new tier in llm.py is all
that's needed — no pipeline logic changes required.
"""

import logging
import threading
from typing import Optional, Callable

from agents import (
    RouterAgent, ClarifierAgent, ArchitectAgent,
    CriticAgent, OperatorAgent, AuditorAgent,
    ValidatorAgent, CompilerAgent, PDFExtractorAgent, QAAgent
)
from roles import get_role_preamble
from llm import apply_tier, is_agent_active, get_active_tier
import subscription_manager as sm

logger = logging.getLogger(__name__)

try:
    import knowledge_db as kdb
    import knowledge_agent as ka
    KNOWLEDGE_AVAILABLE = True
except ImportError:
    KNOWLEDGE_AVAILABLE = False
    logger.info("[Pipeline] Knowledge Engine not available — running without it")


# ═══════════════════════════════════════════════════
# RESULT HELPERS
# ═══════════════════════════════════════════════════

def _base_result(mode="default", role_id="default", complexity="medium") -> dict:
    return {
        "success":           False,
        "output":            None,
        "output_parsed":     None,
        "extracted_goal":    None,
        "critic_status":     None,
        "critic_issues":     [],
        "operator_used":     False,
        "validation":        None,
        "agents_used":       [],
        "mode":              mode,
        "role_id":           role_id,
        "complexity":        complexity,
        "tier":              get_active_tier()["label"],
        "error":             None,
        "knowledge_used":    False,
        "knowledge_context": None,
    }

def _error_result(msg, mode="default", role_id="default", complexity="medium") -> dict:
    r = _base_result(mode, role_id, complexity)
    r["error"] = msg
    return r


# ═══════════════════════════════════════════════════
# PIPELINE
# ═══════════════════════════════════════════════════

class WorkflowPipeline:

    def __init__(self):
        self.router    = RouterAgent()
        self.clarifier = ClarifierAgent()
        self.architect = ArchitectAgent()
        self.critic    = CriticAgent()
        self.operator  = OperatorAgent()
        self.auditor   = AuditorAgent()
        self.validator = ValidatorAgent()
        self.compiler  = CompilerAgent()
        self.extractor = PDFExtractorAgent()
        self.qa        = QAAgent()

        self.knowledge_enabled = KNOWLEDGE_AVAILABLE
        if self.knowledge_enabled:
            kdb.init_storage()

        logger.info(f"[Pipeline] Initialized (Knowledge: {'ON' if self.knowledge_enabled else 'OFF'})")

    # ─────────────────────────────────────────────
    # INTERNAL: route + apply tier
    # ─────────────────────────────────────────────
    def _route(self, user_id: str, text: str, role_preamble: Optional[str] = None) -> dict:
        """
        Runs Router then immediately applies the matching tier.
        Every pipeline entry point calls this first.
        """
        try:
            router_data = self.router.run(user_id, text, role_preamble=role_preamble)
        except Exception as e:
            logger.error(f"[Pipeline] Router failed: {e} — defaulting to medium")
            router_data = {
                "complexity":          "medium",
                "mode":                "default",
                "pipeline_depth":      "standard",
                "needs_clarification": False,
            }

        complexity = router_data.get("complexity", "medium")
        apply_tier(complexity)   # ← upgrades/downgrades all agent models + active set

        tier = get_active_tier()
        logger.info(f"[Pipeline] {tier['label']} tier active — {tier['agent_count']} agents")

        return router_data

    # ─────────────────────────────────────────────
    # PUBLIC: get clarifying questions
    # ─────────────────────────────────────────────
    def get_clarifications(self, user_id: str, goal: str, role_id: str = "default") -> dict:
        can_run, msg = sm.can_execute(user_id)
        if not can_run:
            return _error_result(f"Subscription error: {msg}", role_id=role_id)

        preamble    = get_role_preamble(role_id)
        router_data = self._route(user_id, goal, role_preamble=preamble)

        mode       = router_data.get("mode", "default")
        complexity = router_data.get("complexity", "medium")
        needs      = router_data.get("needs_clarification", False)

        questions = []
        if needs and is_agent_active("clarifier"):
            try:
                questions = self.clarifier.run(user_id, goal, role_preamble=preamble).get("questions", [])
            except Exception as e:
                logger.warning(f"[Pipeline] Clarifier failed: {e}")

        return {
            "needs_clarification": needs,
            "questions":           questions,
            "mode":                mode,
            "complexity":          complexity,
            "tier":                get_active_tier()["label"],
            "role_id":             role_id,
            "router":              router_data,
        }

    # ─────────────────────────────────────────────
    # PUBLIC: run goal pipeline
    # ─────────────────────────────────────────────
    def run(self, user_id: str, goal: str, mode: str = "default", answers: dict = None,
            on_step: Callable = None, role_id: str = "default", thread_id: str = None) -> dict:

        can_run, msg = sm.can_execute(user_id)
        if not can_run:
            return _error_result(f"Subscription error: {msg}", role_id=role_id)

        preamble    = get_role_preamble(role_id)
        router_data = self._route(user_id, goal, role_preamble=preamble)
        complexity  = router_data.get("complexity", "medium")

        enriched_goal = goal
        if answers:
            lines = [
                f"- {k.replace('_', ' ').title()}: {v}"
                for k, v in answers.items() if v and v.strip()
            ]
            if lines:
                enriched_goal = f"{goal}\n\nAdditional context:\n" + "\n".join(lines)

        return self._run_pipeline(
            user_id, enriched_goal, mode=mode, on_step=on_step,
            role_preamble=preamble, role_id=role_id, complexity=complexity,
            thread_id=thread_id
        )

    # ─────────────────────────────────────────────
    # PUBLIC: run document pipeline
    # ─────────────────────────────────────────────
    def run_from_document(self, user_id: str, raw_text: str, on_step: Callable = None,
                          role_id: str = "default") -> dict:
        can_run, msg = sm.can_execute(user_id)
        if not can_run:
            return _error_result(f"Subscription error: {msg}", role_id=role_id)

        preamble = get_role_preamble(role_id)

        def step(name):
            logger.info(f"[Pipeline] {name}")
            if on_step: on_step(name)

        step("Extractor")
        try:
            extracted_goal = self.extractor.run(user_id, raw_text, role_preamble=preamble)
        except Exception as e:
            return _error_result(f"Extractor failed: {e}", role_id=role_id)

        if not extracted_goal or not extracted_goal.strip():
            return _error_result("Extractor returned empty goal", role_id=role_id)

        router_data = self._route(user_id, extracted_goal, role_preamble=preamble)
        mode        = router_data.get("mode", "default")
        complexity  = router_data.get("complexity", "medium")

        result = self._run_pipeline(
            user_id, extracted_goal, mode=mode, on_step=on_step,
            role_preamble=preamble, role_id=role_id, complexity=complexity
        )
        result["extracted_goal"] = extracted_goal

        if self.knowledge_enabled and result.get("success"):
            try:
                doc_id   = kdb.create_node(
                    user_id=user_id,
                    node_type="document",
                    content={"source_type": "text", "extracted_goal": extracted_goal}
                )
                doc_node = kdb.get_node(user_id, doc_id, update_access=False)
                ka.auto_link_node(user_id, doc_id, doc_node)
                result["document_node_id"] = doc_id
            except Exception as e:
                logger.warning(f"[Pipeline] Could not store document: {e}")

        return result

    # ─────────────────────────────────────────────
    # PUBLIC: adaptive Q&A
    # ─────────────────────────────────────────────
    def run_adaptive(self, user_id: str, user_input: str, on_step: Callable = None,
                     role_id: str = "default") -> dict:
        can_run, msg = sm.can_execute(user_id)
        if not can_run:
            return _error_result(f"Subscription error: {msg}", role_id=role_id)

        preamble    = get_role_preamble(role_id)
        router_data = self._route(user_id, user_input, role_preamble=preamble)

        mode       = router_data.get("mode", "default")
        complexity = router_data.get("complexity", "medium")

        def step(name):
            logger.info(f"[Pipeline] {name}")
            if on_step: on_step(name)

        # ⚡ Fast + ⚖ Standard → QA agent only for adaptive
        if complexity in ("simple", "medium"):
            step("QA")
            try:
                answer = self.qa.run(
                    user_id, user_input, complexity=complexity,
                    mode=mode, role_preamble=preamble
                )
                return {
                    "success":    True,
                    "output":     answer,
                    "mode":       mode,
                    "role_id":    role_id,
                    "complexity": complexity,
                    "tier":       get_active_tier()["label"],
                    "agents_used": ["router", "qa"],
                    "error":      None,
                }
            except Exception as e:
                return _error_result(f"QA failed: {e}", mode, role_id, complexity)

        # 🧠 Deep → full pipeline
        return self._run_pipeline(
            user_id, user_input, mode=mode, on_step=on_step,
            role_preamble=preamble, role_id=role_id, complexity=complexity
        )

    # ─────────────────────────────────────────────
    # INTERNAL: core pipeline with tier gating
    # ─────────────────────────────────────────────
    def _run_pipeline(self, user_id: str, goal: str, mode: str = "default",
                      on_step: Callable = None,
                      role_preamble: Optional[str] = None,
                      role_id: str = "default",
                      complexity: str = "medium",
                      thread_id: str = None) -> dict:

        def step(name):
            logger.info(f"[Pipeline] {name}")
            if on_step: on_step(name)

        result = _base_result(mode, role_id, complexity)

        try:
            # ─── KNOWLEDGE (Deep tier only) ───────────────
            context_nodes = None
            if self.knowledge_enabled and is_agent_active("knowledge_retriever"):
                step("Knowledge check")
                try:
                    dup_check = ka.check_before_create(user_id, goal)

                    if dup_check["action"] == "reuse":
                        existing = dup_check["existing_node"]
                        edges    = kdb.get_node_edges(
                            user_id, existing["id"], direction="incoming", edge_type="derives_from"
                        )
                        if edges:
                            workflow = kdb.get_node(user_id, edges[0]["from_node"], update_access=True)
                            if workflow:
                                result["knowledge_used"] = True
                                result["output_parsed"]  = workflow["content"]
                                result["output"] = (
                                    f"## REUSING EXISTING PLAN\n\n"
                                    f"Originally created {workflow['created_at'][:10]} — "
                                    f"{dup_check['similarity']:.0%} match\n\n"
                                ) + self.compiler.run(
                                    user_id, workflow["content"], goal,
                                    mode=mode, role_preamble=role_preamble
                                )
                                result["success"] = True
                                return result

                    elif dup_check["action"] == "evolve":
                        result["knowledge_context"] = {
                            "action":        "evolve",
                            "existing_node": dup_check["existing_node"],
                            "similarity":    dup_check["similarity"],
                        }

                    context_nodes = ka.get_context_for_pipeline(user_id, goal)
                    if context_nodes:
                        result["knowledge_used"] = True

                except Exception as e:
                    logger.warning(f"[Pipeline] Knowledge check failed (continuing): {e}")

            # ─── CLARIFIER (Standard + Deep) ──────────────
            if is_agent_active("clarifier"):
                step("Clarifier")
                result["agents_used"].append("Clarifier")

            # ─── ARCHITECT (Standard + Deep) ──────────────
            if not is_agent_active("architect"):
                # ⚡ Fast tier — go straight to QA
                step("QA (fast tier)")
                result["agents_used"].append("QA")
                try:
                    answer = self.qa.run(
                        user_id, goal, complexity=complexity,
                        mode=mode, role_preamble=role_preamble
                    )
                    result["output"]  = answer
                    result["success"] = True
                    return result
                except Exception as e:
                    return _error_result(f"QA failed: {e}", mode, role_id, complexity)

            step("Architect")
            result["agents_used"].append("Architect")
            try:
                blueprint = self.architect.run(
                    user_id, goal, context_nodes=context_nodes, role_preamble=role_preamble
                )
            except Exception as e:
                return _error_result(f"Architect failed: {e}", mode, role_id, complexity)

            # ─── CRITIC (Standard + Deep) ─────────────────
            critique = {"status": "pass", "issues": []}
            if is_agent_active("critic"):
                step("Critic")
                result["agents_used"].append("Critic")
                try:
                    critique = self.critic.run(
                        user_id, blueprint, original_goal=goal, role_preamble=role_preamble
                    )
                except Exception as e:
                    logger.warning(f"[Pipeline] Critic failed: {e} — skipping")

            result["critic_status"] = critique.get("status", "pass")
            result["critic_issues"] = critique.get("issues", [])

            # ─── OPERATOR (Deep only) ─────────────────────
            if (is_agent_active("operator")
                    and critique.get("status") == "fail"
                    and critique.get("issues")):
                step("Operator")
                result["agents_used"].append("Operator")
                try:
                    blueprint = self.operator.run(
                        user_id, blueprint, issues=critique["issues"],
                        original_goal=goal, role_preamble=role_preamble
                    )
                    result["operator_used"] = True
                    logger.info(f"[Pipeline] Operator fixed {len(critique['issues'])} issues")
                except Exception as e:
                    logger.warning(f"[Pipeline] Operator failed: {e}")
            else:
                if not is_agent_active("operator"):
                    step("Operator skipped (tier)")
                else:
                    step("Operator skipped (no issues)")

            # ─── AUDITOR (Deep only) ──────────────────────
            if is_agent_active("auditor"):
                step("Auditor")
                result["agents_used"].append("Auditor")
                try:
                    blueprint = self.auditor.run(
                        user_id, blueprint, original_goal=goal, role_preamble=role_preamble
                    )
                except Exception as e:
                    logger.warning(f"[Pipeline] Auditor failed: {e}")

            # ─── VALIDATOR (Standard + Deep) ──────────────
            validation = {"status": "pass"}
            if is_agent_active("validator"):
                step("Validator")
                result["agents_used"].append("Validator")
                try:
                    validation = self.validator.run(user_id, blueprint, role_preamble=role_preamble)
                except Exception as e:
                    logger.warning(f"[Pipeline] Validator failed: {e}")

            result["validation"] = validation
            if validation.get("status") != "pass":
                return _error_result(
                    f"Validation failed: {validation.get('reason', 'Schema error')}",
                    mode, role_id, complexity
                )

            result["output_parsed"] = blueprint

            # ─── COMPILER (Standard + Deep) ───────────────
            step("Compiler")
            result["agents_used"].append("Compiler")
            try:
                compiled = self.compiler.run(
                    user_id, blueprint, original_goal=goal, mode=mode,
                    context_nodes=context_nodes, role_preamble=role_preamble
                )
            except Exception as e:
                return _error_result(f"Compiler failed: {e}", mode, role_id, complexity)

            if not compiled or not compiled.strip():
                return _error_result("Compiler returned empty output", mode, role_id, complexity)

            result["output"]  = compiled
            result["success"] = True

            # ─── KNOWLEDGE STORAGE (Deep only) ────────────
            if self.knowledge_enabled and is_agent_active("knowledge_retriever"):
                step("Storing in knowledge base")
                try:
                    goal_id     = kdb.create_node(
                        user_id=user_id,
                        node_type="goal",
                        content={
                            "original_input": goal,
                            "clarified_goal": goal,
                            "mode":           mode,
                            "role_id":        role_id,
                            "complexity":     complexity,
                        },
                        conversation_id=thread_id,
                    )
                    workflow_id = kdb.create_node(
                        user_id=user_id,
                        node_type="workflow",
                        content=blueprint,
                        metadata={"mode": mode, "role_id": role_id, "complexity": complexity},
                        conversation_id=thread_id,
                    )
                    kdb.create_edge(
                        user_id=user_id,
                        from_node=workflow_id, to_node=goal_id,
                        edge_type="derives_from", strength=1.0,
                        reason="Workflow created for goal"
                    )
                    goal_node     = kdb.get_node(user_id, goal_id, update_access=False)
                    workflow_node = kdb.get_node(user_id, workflow_id, update_access=False)
                    ka.auto_link_node(user_id, goal_id, goal_node)
                    ka.auto_link_node(user_id, workflow_id, workflow_node)

                    result["goal_node_id"]     = goal_id
                    result["workflow_node_id"] = workflow_id

                    stats = kdb.get_stats(user_id)
                    if stats["total_nodes"] > 0 and stats["total_nodes"] % 10 == 0:
                        ka.generate_insights(user_id)

                except Exception as e:
                    logger.warning(f"[Pipeline] Knowledge storage failed (non-fatal): {e}")

            step("Complete")
            return result

        except Exception as e:
            logger.error(f"[Pipeline] Unexpected error: {e}", exc_info=True)
            return _error_result(f"Pipeline error: {e}", mode, role_id, complexity)


# ═══════════════════════════════════════════════════
# THREAD-SAFE SINGLETON
# ═══════════════════════════════════════════════════

_pipeline_instance = None
_pipeline_lock     = threading.Lock()

def get_pipeline() -> WorkflowPipeline:
    global _pipeline_instance
    if _pipeline_instance is None:
        with _pipeline_lock:
            if _pipeline_instance is None:
                _pipeline_instance = WorkflowPipeline()
    return _pipeline_instance

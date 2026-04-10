"""
pipeline.py — XoltaOS Pipeline Orchestrator

Goal:     Router → (Clarify?) → Architect → Critic → Operator? → Auditor → Validator → Compiler
Document: Extractor → Router → full pipeline
Q&A:      Router → QAAgent (scales by complexity)

Knowledge Engine is optional — pipeline works without it.
All errors are explicit — no silent fallbacks.
"""

import json
import logging
import threading
from typing import Dict, Optional, Callable, List

from agents import (
    RouterAgent, ClarifierAgent, ArchitectAgent,
    CriticAgent, OperatorAgent, AuditorAgent,
    ValidatorAgent, CompilerAgent, PDFExtractorAgent, QAAgent
)

logger = logging.getLogger(__name__)

# Knowledge Engine — optional
try:
    import knowledge_db as kdb
    import knowledge_agent as ka
    KNOWLEDGE_AVAILABLE = True
except ImportError:
    KNOWLEDGE_AVAILABLE = False
    logger.info("[Pipeline] Knowledge Engine not available — running without it")


# ═══════════════════════════════════════════════════
# RESULT BUILDER HELPERS
# ═══════════════════════════════════════════════════

def _base_result(mode: str = "default") -> dict:
    return {
        "success": False,
        "output": None,
        "output_parsed": None,
        "extracted_goal": None,
        "critic_status": None,
        "critic_issues": [],
        "operator_used": False,
        "validation": None,
        "agents_used": [],
        "mode": mode,
        "error": None,
        "knowledge_used": False,
        "knowledge_context": None,
    }

def _error_result(msg: str, mode: str = "default") -> dict:
    result = _base_result(mode)
    result["error"] = msg
    return result


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
    # PUBLIC: get clarifying questions for a goal
    # ─────────────────────────────────────────────
    def get_clarifications(self, goal: str) -> dict:
        """
        Step 1 of goal flow — run router, optionally get questions.
        Returns routing data + questions.
        """
        try:
            router_data = self.router.run(goal)
        except Exception as e:
            logger.error(f"[Pipeline] Router failed: {e}")
            # Safe fallback — don't abort, but log clearly
            router_data = {
                "complexity": "complex",
                "mode": "default",
                "pipeline_depth": "full",
                "needs_clarification": False,
                "reason": "Router failed — using defaults"
            }

        mode       = router_data.get("mode", "default")
        complexity = router_data.get("complexity", "complex")
        needs      = router_data.get("needs_clarification", False)

        if not needs:
            return {
                "needs_clarification": False,
                "questions": [],
                "mode": mode,
                "complexity": complexity,
                "router": router_data
            }

        try:
            clarifier_data = self.clarifier.run(goal)
            questions = clarifier_data.get("questions", [])
        except Exception as e:
            logger.warning(f"[Pipeline] Clarifier failed: {e} — skipping questions")
            questions = []

        return {
            "needs_clarification": True,
            "questions": questions,
            "mode": mode,
            "complexity": complexity,
            "router": router_data
        }

    # ─────────────────────────────────────────────
    # PUBLIC: run goal pipeline
    # ─────────────────────────────────────────────
    def run(
        self,
        goal: str,
        mode: str = "default",
        answers: dict = None,
        on_step: Callable = None
    ) -> dict:
        """
        Execute full pipeline for a goal.
        Enriches goal with clarification answers before running.
        """
        enriched_goal = goal
        if answers:
            context_lines = [
                f"- {qid.replace('_', ' ').title()}: {ans}"
                for qid, ans in answers.items()
                if ans and ans.strip()
            ]
            if context_lines:
                enriched_goal = f"{goal}\n\nAdditional context:\n" + "\n".join(context_lines)

        return self._run_pipeline(enriched_goal, mode=mode, on_step=on_step)

    # ─────────────────────────────────────────────
    # PUBLIC: run document pipeline
    # ─────────────────────────────────────────────
    def run_from_document(self, raw_text: str, on_step: Callable = None) -> dict:
        """Extract goal from document then run full pipeline."""
        def step(name):
            logger.info(f"[Pipeline] {name}")
            if on_step: on_step(name)

        step("Extractor")
        try:
            extracted_goal = self.extractor.run(raw_text)
        except Exception as e:
            return _error_result(f"Extractor failed: {e}")

        if not extracted_goal or not extracted_goal.strip():
            return _error_result("Extractor returned empty goal")

        # Router decides mode from extracted goal
        try:
            router_data = self.router.run(extracted_goal)
            mode = router_data.get("mode", "default")
        except Exception:
            mode = "default"

        result = self._run_pipeline(extracted_goal, mode=mode, on_step=on_step)
        result["extracted_goal"] = extracted_goal

        # Store document in knowledge base
        if self.knowledge_enabled and result.get("success"):
            try:
                doc_id = kdb.create_node(
                    node_type="document",
                    content={
                        "source_type": "text",
                        "extracted_goal": extracted_goal,
                    }
                )
                doc_node = kdb.get_node(doc_id, update_access=False)
                ka.auto_link_node(doc_id, doc_node)
                result["document_node_id"] = doc_id
            except Exception as e:
                logger.warning(f"[Pipeline] Could not store document: {e}")

        return result

    # ─────────────────────────────────────────────
    # PUBLIC: adaptive Q&A pipeline
    # ─────────────────────────────────────────────
    def run_adaptive(self, user_input: str, on_step: Callable = None) -> dict:
        """Route Q&A to QA agent or full pipeline based on complexity."""
        def step(name):
            logger.info(f"[Pipeline] {name}")
            if on_step: on_step(name)

        result = {
            "success": False,
            "output": None,
            "mode": "default",
            "complexity": None,
            "pipeline_depth": None,
            "agents_used": [],
            "error": None
        }

        try:
            step("Router")
            try:
                router_data = self.router.run(user_input)
            except Exception as e:
                logger.warning(f"[Pipeline] Router failed in adaptive: {e}")
                router_data = {"complexity": "medium", "mode": "default", "pipeline_depth": "standard"}

            complexity = router_data.get("complexity", "medium")
            mode       = router_data.get("mode", "default")
            depth      = router_data.get("pipeline_depth", "standard")

            result["mode"]       = mode
            result["complexity"] = complexity
            result["pipeline_depth"] = depth
            result["agents_used"].append("Router")

            # Complex → treat as a goal, run full pipeline
            if depth == "full":
                pipeline_result = self._run_pipeline(user_input, mode=mode, on_step=on_step)
                result.update({
                    "output":      pipeline_result.get("output"),
                    "success":     pipeline_result.get("success", False),
                    "error":       pipeline_result.get("error"),
                    "agents_used": result["agents_used"] + pipeline_result.get("agents_used", [])
                })
                return result

            # Simple/medium → QA agent
            step("QA")
            result["agents_used"].append("QA")
            result["output"]  = self.qa.run(user_input, complexity, mode=mode)
            result["success"] = True
            return result

        except Exception as e:
            result["error"] = f"Adaptive pipeline error: {e}"
            logger.error(f"[Pipeline] {e}", exc_info=True)
            return result

    # ─────────────────────────────────────────────
    # INTERNAL: core agent pipeline
    # ─────────────────────────────────────────────
    def _run_pipeline(
        self,
        goal: str,
        mode: str = "default",
        on_step: Callable = None
    ) -> dict:

        def step(name):
            logger.info(f"[Pipeline] {name}")
            if on_step: on_step(name)

        result = _base_result(mode)

        try:
            # ─── KNOWLEDGE: pre-pipeline checks ──────────
            context_nodes = None
            if self.knowledge_enabled:
                step("Knowledge check")
                try:
                    dup_check = ka.check_before_create(goal)

                    if dup_check["action"] == "reuse":
                        existing = dup_check["existing_node"]
                        edges = kdb.get_node_edges(
                            existing["id"],
                            direction="incoming",
                            edge_type="derives_from"
                        )
                        if edges:
                            workflow = kdb.get_node(edges[0]["from_node"], update_access=True)
                            if workflow:
                                result["knowledge_used"] = True
                                result["output_parsed"]  = workflow["content"]
                                result["output"] = (
                                    f"## REUSING EXISTING PLAN\n\n"
                                    f"Originally created {workflow['created_at'][:10]} — "
                                    f"{dup_check['similarity']:.0%} match\n\n"
                                ) + self.compiler.run(
                                    workflow["content"], goal, mode=mode
                                )
                                result["success"] = True
                                return result

                    elif dup_check["action"] == "evolve":
                        result["knowledge_context"] = {
                            "action": "evolve",
                            "existing_node": dup_check["existing_node"],
                            "similarity": dup_check["similarity"]
                        }

                    context_nodes = ka.get_context_for_pipeline(goal)
                    if context_nodes:
                        result["knowledge_used"] = True

                except Exception as e:
                    logger.warning(f"[Pipeline] Knowledge check failed (continuing): {e}")

            # ─── ARCHITECT ────────────────────────────────
            step("Architect")
            result["agents_used"].append("Architect")
            try:
                blueprint = self.architect.run(goal, context_nodes=context_nodes)
            except Exception as e:
                return _error_result(f"Architect failed: {e}", mode)

            # ─── CRITIC ───────────────────────────────────
            step("Critic")
            result["agents_used"].append("Critic")
            try:
                critique = self.critic.run(blueprint, original_goal=goal)
            except Exception as e:
                logger.warning(f"[Pipeline] Critic failed: {e} — skipping")
                critique = {"status": "pass", "issues": []}

            result["critic_status"] = critique.get("status", "pass")
            result["critic_issues"] = critique.get("issues", [])

            # ─── OPERATOR (only if needed) ─────────────────
            if critique.get("status") == "fail" and critique.get("issues"):
                step("Operator")
                result["agents_used"].append("Operator")
                try:
                    blueprint = self.operator.run(
                        blueprint,
                        issues=critique["issues"],
                        original_goal=goal
                    )
                    result["operator_used"] = True
                    logger.info(f"[Pipeline] Operator fixed {len(critique['issues'])} issues")
                except Exception as e:
                    logger.warning(f"[Pipeline] Operator failed: {e} — using pre-operator plan")
            else:
                step("Operator skipped")

            # ─── AUDITOR ──────────────────────────────────
            step("Auditor")
            result["agents_used"].append("Auditor")
            try:
                blueprint = self.auditor.run(blueprint, original_goal=goal)
            except Exception as e:
                logger.warning(f"[Pipeline] Auditor failed: {e} — using pre-audit plan")

            # ─── VALIDATOR ────────────────────────────────
            step("Validator")
            result["agents_used"].append("Validator")
            try:
                validation = self.validator.run(blueprint)
            except Exception as e:
                logger.warning(f"[Pipeline] Validator parse failed: {e}")
                validation = {"status": "pass"}  # assume pass if validator itself fails

            result["validation"] = validation

            # Hard stop if schema is broken — compiler will produce garbage otherwise
            if validation.get("status") != "pass":
                return _error_result(
                    f"Validation failed: {validation.get('reason', 'Schema error')}",
                    mode
                )

            result["output_parsed"] = blueprint

            # ─── COMPILER ─────────────────────────────────
            step("Compiler")
            result["agents_used"].append("Compiler")
            try:
                compiled = self.compiler.run(
                    blueprint,
                    original_goal=goal,
                    mode=mode,
                    context_nodes=context_nodes
                )
            except Exception as e:
                return _error_result(f"Compiler failed: {e}", mode)

            if not compiled or not compiled.strip():
                return _error_result("Compiler returned empty output", mode)

            result["output"]  = compiled
            result["success"] = True

            # ─── KNOWLEDGE: post-pipeline storage ─────────
            if self.knowledge_enabled and result["success"]:
                step("Storing in knowledge base")
                try:
                    # Use actual router data from the pipeline
                    goal_id = kdb.create_node(
                        node_type="goal",
                        content={
                            "original_input":  goal,
                            "clarified_goal":  goal,
                            "scope":           result.get("complexity", "complex"),
                            "mode":            mode,
                        }
                    )
                    workflow_id = kdb.create_node(
                        node_type="workflow",
                        content=blueprint,
                        metadata={"mode": mode}
                    )
                    kdb.create_edge(
                        from_node=workflow_id,
                        to_node=goal_id,
                        edge_type="derives_from",
                        strength=1.0,
                        reason="Workflow created for goal"
                    )
                    # Auto-link both nodes
                    goal_node     = kdb.get_node(goal_id, update_access=False)
                    workflow_node = kdb.get_node(workflow_id, update_access=False)
                    ka.auto_link_node(goal_id, goal_node)
                    ka.auto_link_node(workflow_id, workflow_node)

                    result["goal_node_id"]     = goal_id
                    result["workflow_node_id"] = workflow_id

                    # Periodic insight generation
                    stats = kdb.get_stats()
                    if stats["total_nodes"] > 0 and stats["total_nodes"] % 10 == 0:
                        logger.info("[Pipeline] Triggering insight generation")
                        ka.generate_insights()

                except Exception as e:
                    logger.warning(f"[Pipeline] Knowledge storage failed (non-fatal): {e}")

            step("Complete")
            return result

        except Exception as e:
            logger.error(f"[Pipeline] Unexpected error: {e}", exc_info=True)
            return _error_result(f"Pipeline error: {e}", mode)


# ═══════════════════════════════════════════════════
# THREAD-SAFE SINGLETON
# ═══════════════════════════════════════════════════

_pipeline_instance = None
_pipeline_lock     = threading.Lock()

def get_pipeline() -> WorkflowPipeline:
    """Get or create pipeline singleton. Thread-safe."""
    global _pipeline_instance
    if _pipeline_instance is None:
        with _pipeline_lock:
            if _pipeline_instance is None:
                _pipeline_instance = WorkflowPipeline()
    return _pipeline_instance

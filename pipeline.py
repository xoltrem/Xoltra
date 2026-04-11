"""pipeline.py — XoltaOS execution pipeline."""

import logging
from typing import Optional, Dict, List

import roles
import knowledge_db as kdb
import knowledge_agent
from agents import (
    RouterAgent,
    ClarifierAgent,
    PDFExtractorAgent,
    ArchitectAgent,
    CriticAgent,
    OperatorAgent,
    ValidatorAgent,
    CompilerAgent,
    QAAgent,
)

logger = logging.getLogger(__name__)

class Pipeline:
    def __init__(self):
        kdb.init_storage()
        self.router = RouterAgent()
        self.clarifier = ClarifierAgent()
        self.extractor = PDFExtractorAgent()
        self.architect = ArchitectAgent()
        self.critic = CriticAgent()
        self.operator = OperatorAgent()
        self.validator = ValidatorAgent()
        self.compiler = CompilerAgent()
        self.qa = QAAgent()

    def get_clarifications(self, goal: str, role_id: str = "default") -> Dict:
        role_preamble = roles.get_role_preamble(role_id)
        if not goal or not goal.strip():
            return {"mode": "default", "questions": []}

        try:
            response = self.clarifier.run(goal.strip(), role_preamble=role_preamble)
            if not isinstance(response, dict):
                raise ValueError("Clarifier returned invalid response")
            mode = response.get("mode", "default")
            questions = response.get("questions", [])
            if not isinstance(questions, list):
                questions = []
            if mode not in ("default", "coach"):
                mode = "default"
            return {"mode": mode, "questions": questions}
        except Exception as exc:
            logger.warning(f"[Pipeline] Clarification failed: {exc}")
            return {"mode": "default", "questions": []}

    def run(
        self,
        goal: str,
        mode: str = "default",
        answers: Optional[Dict] = None,
        role_id: str = "default",
        on_step=None,
    ) -> Dict:
        role_preamble = roles.get_role_preamble(role_id)
        answers = answers or {}
        result = {
            "success": False,
            "output": "",
            "output_parsed": None,
            "mode": mode,
            "role_id": role_id,
            "critic_status": "pass",
            "operator_used": False,
            "critic_issues": [],
            "error": None,
        }

        if not goal or not goal.strip():
            result["error"] = "Goal is required"
            return result

        clarified_goal = self._prepare_clarified_goal(goal, answers)
        if on_step:
            on_step("goal_saved")

        try:
            kdb.create_node(
                node_type="goal",
                content={
                    "original_input": goal.strip(),
                    "clarified_goal": clarified_goal,
                    "answers": answers,
                },
            )
        except Exception as exc:
            logger.warning(f"[Pipeline] Goal storage failed: {exc}")

        context_nodes = knowledge_agent.get_context_for_pipeline(clarified_goal)

        try:
            if on_step:
                on_step("architect")
            blueprint = self.architect.run(
                clarified_goal,
                context_nodes=context_nodes,
                role_preamble=role_preamble,
            )
            if not isinstance(blueprint, dict):
                raise ValueError("Architect returned invalid blueprint")
            result["output_parsed"] = blueprint

            if on_step:
                on_step("critic")
            critique = self.critic.run(
                blueprint,
                clarified_goal,
                role_preamble=role_preamble,
            )
            status = critique.get("status", "pass") if isinstance(critique, dict) else "pass"
            issues = critique.get("issues", []) if isinstance(critique, dict) else []
            if not isinstance(issues, list):
                issues = []
            result["critic_status"] = status
            result["critic_issues"] = issues

            if issues:
                if on_step:
                    on_step("operator")
                blueprint = self.operator.run(
                    blueprint,
                    issues,
                    clarified_goal,
                    role_preamble=role_preamble,
                )
                result["operator_used"] = True
                result["output_parsed"] = blueprint

            if on_step:
                on_step("validate")
            validation = self.validator.run(
                blueprint,
                role_preamble=role_preamble,
            )
            if not isinstance(validation, dict):
                raise ValueError("Validator returned invalid response")
            if validation.get("status") != "pass":
                result["error"] = validation.get("reason", "Validation failed")

            if on_step:
                on_step("compile")
            compiled = self.compiler.run(
                blueprint,
                clarified_goal,
                mode=mode,
                context_nodes=context_nodes,
                role_preamble=role_preamble,
            )
            result["output"] = compiled
            result["success"] = bool(compiled)

            try:
                workflow_id = kdb.create_node(
                    node_type="workflow",
                    content={
                        "goal_summary": blueprint.get("goal_summary", ""),
                        "phases": blueprint.get("phases", []),
                        "original_goal": goal.strip(),
                        "clarified_goal": clarified_goal,
                    },
                )
                knowledge_agent.auto_link_node(
                    workflow_id,
                    {
                        "type": "workflow",
                        "content": {
                            "goal_summary": blueprint.get("goal_summary", ""),
                            "phases": blueprint.get("phases", []),
                        },
                    },
                )
            except Exception as exc:
                logger.warning(f"[Pipeline] Workflow storage/linking failed: {exc}")

            return result
        except Exception as exc:
            logger.error(f"[Pipeline] Run failed: {exc}", exc_info=True)
            result["error"] = str(exc)
            return result

    def run_from_document(self, text: str, role_id: str = "default", on_step=None) -> Dict:
        role_preamble = roles.get_role_preamble(role_id)
        if not text or not text.strip():
            return {
                "success": False,
                "output": "",
                "output_parsed": None,
                "extracted_goal": "",
                "mode": "default",
                "role_id": role_id,
                "error": "Document text is required",
            }

        try:
            if on_step:
                on_step("extract_document")
            extracted_goal = self.extractor.run(text, role_preamble=role_preamble)
            extracted_goal = extracted_goal.strip()
            if not extracted_goal:
                raise ValueError("Could not extract a goal from the document")

            document_id = kdb.create_node(
                node_type="document",
                content={
                    "source_text": text[:5000],
                    "extracted_goal": extracted_goal,
                },
            )

            result = self.run(
                extracted_goal,
                mode="default",
                answers={},
                role_id=role_id,
                on_step=on_step,
            )
            result["extracted_goal"] = extracted_goal
            result["document_id"] = document_id
            return result
        except Exception as exc:
            logger.error(f"[Pipeline] Document pipeline failed: {exc}", exc_info=True)
            return {
                "success": False,
                "output": "",
                "output_parsed": None,
                "extracted_goal": "",
                "mode": "default",
                "role_id": role_id,
                "error": str(exc),
            }

    def run_adaptive(self, question: str, role_id: str = "default", on_step=None) -> Dict:
        role_preamble = roles.get_role_preamble(role_id)
        try:
            if on_step:
                on_step("route")
            routing = self.router.run(question, role_preamble=role_preamble)
        except Exception as exc:
            logger.warning(f"[Pipeline] Router failed: {exc}")
            routing = {}

        mode = routing.get("mode", "default")
        complexity = routing.get("complexity", "medium")
        if mode not in ("default", "coach"):
            mode = "default"
        if complexity not in ("simple", "medium", "complex"):
            complexity = "medium"

        try:
            if on_step:
                on_step("qa")
            output = self.qa.run(
                question,
                complexity=complexity,
                mode=mode,
                role_preamble=role_preamble,
            )
            return {
                "output": output,
                "mode": mode,
                "role_id": role_id,
            }
        except Exception as exc:
            logger.error(f"[Pipeline] Q&A failed: {exc}", exc_info=True)
            return {
                "output": "",
                "mode": mode,
                "role_id": role_id,
                "error": str(exc),
            }

    @staticmethod
    def _prepare_clarified_goal(goal: str, answers: Dict) -> str:
        clarified = goal.strip()
        if answers:
            details = []
            for key, value in answers.items():
                if not value:
                    continue
                details.append(f"{key}: {value}")

            if details:
                clarified += "\n\nClarifying details:\n" + "\n".join(details)
        return clarified


def get_pipeline() -> Pipeline:
    return Pipeline()

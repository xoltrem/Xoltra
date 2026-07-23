"""
agents.py — Xolta Agent Definitions

Every agent:
- Receives original_goal where relevant so context is never lost
- Parses its own JSON safely — never trusts raw LLM output
- Raises on failure rather than returning garbage
- Accepts role_preamble: str | None — passed to every LLM call
- Requires user_id for multi-tenant data and token tracking

Two modes:
  default — direct + detailed, leads with answers
  coach   — teaching mode, detected automatically by Router
"""

import json
import logging
from typing import List, Dict, Optional

from llm import (
    safe_json_parse,
    call_router, call_clarifier, call_extractor,
    call_architect, call_critic, call_operator,
    call_auditor, call_validator, call_compiler,
    call_qa, call_knowledge_retriever, call_knowledge_linker,
    call_insight_generator, call_deduplicator,
    call_coding, call_coach,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════
# ROUTER
# ═══════════════════════════════════════════════════

class RouterAgent:

    def run(self, user_id: str, user_input: str,
            role_preamble: Optional[str] = None) -> dict:
        raw = call_router(f"""
You are an intelligent request classifier for an AI execution system.

Analyze the input and classify across four dimensions:

1. COMPLEXITY
   - simple: factual, math, definition, yes/no, single lookup
   - medium: multi-step, comparison, how-to, short planning
   - complex: strategy, execution systems, business plans, research, multi-phase goals

2. MODE — only two options:
   - coach: user wants to LEARN how to do something themselves
     Signals: "teach me", "how do I", "help me learn", "show me how", "guide me"
   - default: everything else

3. PIPELINE_DEPTH
   - minimal: 2 agents — simple factual/calculation
   - standard: 4 agents — medium complexity
   - full: all agents — complex goals, strategies, execution plans

4. NEEDS_CLARIFICATION
   - true: complex goal that needs timeline, budget, team size, or constraints
   - false: everything else

Return ONLY valid JSON, nothing else:
{{
  "complexity": "simple | medium | complex",
  "mode": "default | coach",
  "pipeline_depth": "minimal | standard | full",
  "needs_clarification": true | false,
  "reason": "one sentence"
}}

Input: {user_input}
""", role_preamble=role_preamble)
        return safe_json_parse(raw)


# ═══════════════════════════════════════════════════
# CLARIFIER
# ═══════════════════════════════════════════════════

class ClarifierAgent:

    def run(self, user_id: str, goal: str,
            role_preamble: Optional[str] = None) -> dict:
        raw = call_clarifier( f"""
You are a strategic intake specialist generating clarifying questions before building an execution plan.

Generate 3-5 questions that would significantly improve the plan.
Only ask what matters — infer what you can from the goal.
Cover: timeline, budget, team/resources, constraints, prior attempts, success definition.

Return ONLY valid JSON:
{{
  "questions": [
    {{
      "id": "q1",
      "label": "short label e.g. Timeline",
      "question": "full question text",
      "placeholder": "e.g. 90 days, by end of Q2"
    }}
  ]
}}

Goal: {goal}
""", role_preamble=role_preamble)
        return safe_json_parse(raw)


# ═══════════════════════════════════════════════════
# PDF EXTRACTOR
# ═══════════════════════════════════════════════════

class PDFExtractorAgent:

    def run(self, user_id: str, raw_text: str,
            role_preamble: Optional[str] = None) -> str:
        return call_extractor( f"""
You are a precision document analyst.
Convert raw document text into an actionable goal statement — 3-6 sentences.
Frame it as if a human is describing their goal to a strategic advisor.
Capture: core purpose, constraints, timelines, resources.
Do NOT summarize — frame as an actionable goal.
Output ONLY the goal statement, no preamble.

Raw Text: {raw_text[:6000]}
""", role_preamble=role_preamble)


# ═══════════════════════════════════════════════════
# ARCHITECT
# ═══════════════════════════════════════════════════

class ArchitectAgent:

    def run(
        self,
        user_id: str,
        goal: str,
        context_nodes: Optional[List[Dict]] = None,
        role_preamble: Optional[str] = None
    ) -> dict:

        context_section = ""
        if context_nodes:
            context_section = "\n\n## RELEVANT PAST WORK\n"
            for i, node in enumerate(context_nodes[:3], 1):
                summary   = node.get("content", "")[:200]
                relevance = node.get("relevance", 0)
                created   = node.get("created_at", "")[:10]
                context_section += (
                    f"{i}. [{node['type'].upper()}] {summary}... "
                    f"(relevance: {relevance:.0%}, created: {created})\n"
                )
            context_section += "\nUse these for inspiration. Build a fresh plan for the current goal.\n"

        raw = call_architect( f"""
You are a world-class strategic execution architect.
Transform the goal into a structured execution blueprint.
Output ONLY valid JSON — no preamble, no markdown, no text outside JSON.

Schema:
{{
  "goal_summary": "one crisp sentence — what success looks like",
  "phases": [
    {{
      "phase_name": "string",
      "objective": "string",
      "steps": [
        {{
          "action": "verb-first specific action",
          "why_this_matters": "strategic reason",
          "estimated_time": "e.g. 3 days",
          "difficulty_level": "Low | Medium | High",
          "expected_outcome": "measurable result",
          "suggested_tools": ["string"]
        }}
      ]
    }}
  ],
  "top_risks": [{{"risk": "string", "mitigation": "string"}}],
  "first_72_hours": ["specific action"]
}}

Rules:
- 3-5 phases, 2-4 steps each
- Measurable outcomes with numbers where possible
- 3+ risks, 4+ first_72_hours actions
- No motivational language
- No text outside JSON
{context_section}
Goal: {goal}
""", role_preamble=role_preamble)
        return safe_json_parse(raw)


# ═══════════════════════════════════════════════════
# CRITIC
# ═══════════════════════════════════════════════════

class CriticAgent:

    def run(self, user_id: str, blueprint: dict, original_goal: str,
            role_preamble: Optional[str] = None) -> dict:
        raw = call_critic( f"""
Ruthless plan reviewer. Your job is to find every flaw.

Check for:
- Vague non-verb actions (e.g. "consider" instead of "research and list")
- Unmeasurable outcomes (e.g. "improve sales" instead of "increase sales by 20%")
- Unrealistic timelines for the complexity
- Empty tool lists
- Missing or trivial risks
- Fewer than 2 steps per phase
- Invalid difficulty levels (must be Low/Medium/High only)
- Steps that don't serve the original goal

Original Goal: {original_goal}

Return ONLY JSON:
{{"status": "pass | fail", "issues": ["specific issue description"]}}

If clean: {{"status": "pass", "issues": []}}

Draft Plan: {json.dumps(blueprint)}
""", role_preamble=role_preamble)
        return safe_json_parse(raw)


# ═══════════════════════════════════════════════════
# OPERATOR
# ═══════════════════════════════════════════════════

class OperatorAgent:

    def run(
        self,
        user_id: str,
        blueprint: dict,
        issues: List[str],
        original_goal: str,
        role_preamble: Optional[str] = None
    ) -> dict:
        raw = call_operator( f"""
Pragmatic fixer. Fix every issue listed precisely.

Rules:
- Keep schema exactly intact — same phases, same structure
- Fix vague actions with specific verb-first language
- Add real measurable outcomes with numbers
- Add real named tools (not generic "project management tool")
- Keep the plan serving the original goal
- Return FULL corrected JSON only — no commentary

Original Goal: {original_goal}
Issues to Fix: {json.dumps(issues)}
Draft Plan: {json.dumps(blueprint)}
""", role_preamble=role_preamble)
        return safe_json_parse(raw)


# ═══════════════════════════════════════════════════
# AUDITOR
# ═══════════════════════════════════════════════════

class AuditorAgent:

    def run(self, user_id: str, blueprint: dict, original_goal: str,
            role_preamble: Optional[str] = None) -> dict:
        raw = call_auditor( f"""
Precision auditor. Sharpen without changing structure.

Improve:
- Verb specificity (replace weak verbs with precise ones)
- Measurable outcomes — add numbers wherever possible
- Tool suggestions — replace generic with specific named tools
- Realistic timelines — adjust if clearly off

Do NOT:
- Change the schema
- Remove any steps or phases
- Change the fundamental approach

Original Goal: {original_goal}
Return improved JSON only.

Plan: {json.dumps(blueprint)}
""", role_preamble=role_preamble)
        return safe_json_parse(raw)


# ═══════════════════════════════════════════════════
# VALIDATOR
# ═══════════════════════════════════════════════════

class ValidatorAgent:

    def run(self, user_id: str, blueprint: dict,
            role_preamble: Optional[str] = None) -> dict:
        raw = call_validator( f"""
Strict JSON schema validator. Binary — pass or fail only.

Required fields:
- goal_summary (non-empty string)
- phases (array, minimum 2 items)
  - Each phase: phase_name, objective, steps (array, min 2)
  - Each step: action, why_this_matters, estimated_time, difficulty_level, expected_outcome, suggested_tools
  - difficulty_level must be exactly: Low, Medium, or High
- top_risks (array, min 2 items, each with risk + mitigation)
- first_72_hours (array, min 3 items)

Return ONLY:
{{"status": "pass"}}
OR
{{"status": "fail", "reason": "exact field and issue"}}

JSON to validate: {json.dumps(blueprint)}
""", role_preamble=role_preamble)
        return safe_json_parse(raw)


# ═══════════════════════════════════════════════════
# COMPILER
# ═══════════════════════════════════════════════════

class CompilerAgent:

    def run(
        self,
        user_id: str,
        blueprint: dict,
        original_goal: str,
        mode: str = "default",
        context_nodes: Optional[List[Dict]] = None,
        role_preamble: Optional[str] = None
    ) -> str:

        style = """
You are writing a direct, rich execution document.
- DIRECT: lead with what matters, no filler, no preamble
- DETAILED: full strategic depth, explain the WHY, concrete specifics

Structure EXACTLY:
## EXECUTION SUMMARY
1-2 sentences. What success looks like and the core approach.

## FIRST 72 HOURS
Each action as a detailed paragraph: what to do, why now, how to start today.

## PHASE BREAKDOWN
### Phase [N]: [Phase Name]
**Objective:** one sentence
Each step as a paragraph: specific action + strategic reason + how to execute + tools + measurable outcome.

## TOP RISKS & HOW TO HANDLE THEM
Each risk as a paragraph: what it is, why it happens, exact mitigation.

## START HERE
2 sentences. The single most important thing to do in the next 24 hours.

500-800 words. Paragraphs only. No bullets. Second person. No filler.
"""

        context_footer = ""
        if context_nodes:
            context_footer = "\n\n---\n\n## RELATED PAST WORK\n\n"
            for node in context_nodes[:2]:
                summary   = node.get("content", "")[:150]
                created   = node.get("created_at", "")[:10]
                relevance = node.get("relevance", 0)
                context_footer += (
                    f"**{node['type'].title()}** (created {created}, "
                    f"{relevance:.0%} relevant): {summary}...\n\n"
                )

        compiled = call_compiler( f"""
You are an expert execution strategist and writer.

{style}

Additional rules:
- Second person throughout
- Specific — no vague advice
- No raw JSON in output
- Use ## for sections, ### for phase headers

Original Goal: {original_goal}
Execution Plan: {json.dumps(blueprint)}
""", role_preamble=role_preamble)

        return compiled + context_footer


# ═══════════════════════════════════════════════════
# QA AGENT
# ═══════════════════════════════════════════════════

class QAAgent:

    def run(
        self,
        user_id: str,
        question: str,
        complexity: str = "medium",
        mode: str = "default",
        role_preamble: Optional[str] = None
    ) -> str:

        length = {
            "simple":  "2-4 sentences",
            "medium":  "2-3 paragraphs",
            "complex": "4-6 paragraphs with clear structure"
        }.get(complexity, "2-3 paragraphs")

        return call_qa( f"""
You are a direct, expert responder. Two qualities combined: direct AND detailed.

- Lead with the answer immediately — no preamble
- Give depth, context, and reasoning that makes it genuinely useful
- For calculations: result first, then working
- For facts: state it, then why it matters
- For complex questions: structured explanation with clear reasoning
- No filler, no "great question"
- Length: {length}. Second person where natural.

Question: {question}
""", role_preamble=role_preamble)


# ═══════════════════════════════════════════════════
# COACH AGENT
# ═══════════════════════════════════════════════════

class CoachAgent:

    def run(
        self,
        user_id: str,
        goal: str,
        role_preamble: Optional[str] = None
    ) -> str:
        return call_coach( f"""
You are a world-class Executive Coach. Help the user understand — never just give the answer.

- Break down the key concepts they need
- Ask guiding questions that lead toward the answer
- Give frameworks and mental models they can reuse
- End with one question that pushes them to think deeper
- Second person. Length: 4-6 paragraphs.

Goal/Question: {goal}
""", role_preamble=role_preamble)


# ═══════════════════════════════════════════════════
# CODING AGENT
# ═══════════════════════════════════════════════════

class CodingAgent:

    def run(
        self,
        user_id: str,
        goal: str,
        role_preamble: Optional[str] = None
    ) -> str:
        return call_coding( f"""
You are a master Coding Agent with expertise in every programming language.

Write high-quality, efficient, and well-structured code. 
- Lead with the code immediately
- Provide brief, clear explanations for complex parts
- Ensure all features work as intended

Goal: {goal}
""", role_preamble=role_preamble)


# ═══════════════════════════════════════════════════
# KNOWLEDGE ENGINE AGENTS
# ═══════════════════════════════════════════════════

class KnowledgeLinkerAgent:

    def run(self, user_id: str, source_node: dict, candidate_nodes: list,
            role_preamble: Optional[str] = None) -> dict:
        raw = call_knowledge_linker( f"""
You are a knowledge graph relationship expert.

Analyze if these nodes should be linked and how.

SOURCE NODE:
Type: {source_node.get('type')}
Content: {json.dumps(source_node.get('content', {}))[:400]}

CANDIDATE NODES:
{json.dumps([{{'id': n['id'], 'type': n['type'], 'summary': str(n['content'])[:100]}} for n in candidate_nodes], indent=2)}

For each candidate determine:
1. Should it be linked? (true/false)
2. Edge type: derives_from | relates_to | evolved_from | prerequisite_for | similar_to
3. Strength: 0.0-1.0
4. Reason: one sentence

Return ONLY JSON:
{{
  "links": [
    {{
      "to_node_id": "uuid",
      "should_link": true,
      "edge_type": "relates_to",
      "strength": 0.85,
      "reason": "Both focus on SaaS product launch"
    }}
  ]
}}
""", role_preamble=role_preamble)
        return safe_json_parse(raw)


class DeduplicatorAgent:

    def run(self, user_id: str, goal: str, similar_goals: list,
            role_preamble: Optional[str] = None) -> dict:
        raw = call_deduplicator( f"""
You are a duplication detection specialist.

Analyze if this new goal is essentially the same as existing goals.

NEW GOAL: {goal}

EXISTING SIMILAR GOALS:
{json.dumps([{{'id': g['id'], 'goal': g['content'].get('clarified_goal', ''), 'similarity': g.get('relevance', 0)}} for g in similar_goals], indent=2)}

Decide:
1. duplicate (>95% same — reuse existing)
2. evolution (85-95% similar — build on existing)
3. new (<85% similar — create fresh)

Return ONLY JSON:
{{
  "decision": "duplicate | evolution | new",
  "matched_id": "uuid or null",
  "confidence": 0.0-1.0,
  "reasoning": "one sentence"
}}
""", role_preamble=role_preamble)
        return safe_json_parse(raw)

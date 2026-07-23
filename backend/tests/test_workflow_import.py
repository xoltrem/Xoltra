"""
test_workflow_import.py, the deterministic parts of workflow import: source
detection, step validation, and graph compilation. The LLM call inside
parse_import() needs real Cohere credentials and isn't tested here, see
workflow_import.py's own docstring for why that split exists.
"""

import json

import workflow_import as wi


def test_detects_n8n_export():
    export = json.dumps({
        "nodes": [
            {"name": "Gmail Trigger", "type": "n8n-nodes-base.gmailTrigger", "parameters": {"label": "INBOX"}},
            {"name": "Slack", "type": "n8n-nodes-base.slack", "parameters": {"channel": "#alerts"}},
        ],
        "connections": {}
    })
    source, summary, count = wi._detect_and_summarize(export)
    assert source == "n8n"
    assert count == 2
    assert "Gmail Trigger" in summary


def test_detects_make_blueprint():
    export = json.dumps({"flow": [{"module": "gmail:trigger", "mapper": {"folder": "INBOX"}}]})
    source, _, count = wi._detect_and_summarize(export)
    assert source == "make"
    assert count == 1


def test_freeform_text_falls_through_cleanly():
    source, summary, count = wi._detect_and_summarize("When a new lead comes in, email me a summary.")
    assert source == "freeform"
    assert count == 1
    assert "new lead" in summary


def test_validate_steps_drops_unknown_node_types():
    steps = [
        {"step_index": 0, "label": "Real node", "node_type": "trigger.webhook", "why": "starts it"},
        {"step_index": 1, "label": "Fake node", "node_type": "integration.does_not_exist", "why": "should drop"},
    ]
    valid, warnings = wi._validate_steps(steps)
    assert len(valid) == 1
    assert valid[0]["node_type"] == "trigger.webhook"
    assert len(warnings) == 1


def test_validate_steps_raises_if_nothing_survives():
    steps = [{"step_index": 0, "label": "Fake", "node_type": "not.real", "why": "x"}]
    try:
        wi._validate_steps(steps)
        assert False, "should have raised"
    except RuntimeError:
        pass


def test_compile_wires_synthetic_prompt_node_for_ai_generate():
    steps = [
        {"step_index": 0, "label": "Start", "node_type": "trigger.webhook", "params": {},
         "ai_prompt_template": None, "why": "x", "fidelity": "exact"},
        {"step_index": 1, "label": "Summarize", "node_type": "ai.cohere_generate", "params": {},
         "ai_prompt_template": "Summarize: {{ data }}", "why": "x", "fidelity": "exact"},
    ]
    graph = wi.compile_steps_to_graph(steps)

    node_types = [n["type"] for n in graph["nodes"]]
    assert "utility.transform" in node_types  # the synthetic prompt-bridge node
    assert "ai.cohere_generate" in node_types

    # the edge into ai.cohere_generate must target its "prompt" port specifically,
    # not the generic "data" port, that's the whole point of the bridge.
    ai_node_id = next(n["id"] for n in graph["nodes"] if n["type"] == "ai.cohere_generate")
    edge_into_ai = next(e for e in graph["edges"] if e["target"] == ai_node_id)
    assert edge_into_ai["target_port"] == "prompt"


def test_compile_adds_missing_trigger():
    steps = [{"step_index": 0, "label": "Do a thing", "node_type": "utility.delay", "params": {},
              "ai_prompt_template": None, "why": "x", "fidelity": "exact"}]
    graph = wi.compile_steps_to_graph(steps)
    assert graph["nodes"][0]["type"] == "trigger.manual"

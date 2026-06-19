"""
main.py — XoltaOS CLI Entry Point
Cross-platform (Windows + Unix).
"""

import json
import sys
import os

# ═══════════════════════════════════════════════════
# CROSS-PLATFORM INPUT — no SIGALRM (Unix-only)
# ═══════════════════════════════════════════════════

def safe_input(prompt: str, default: str = "") -> str:
    """
    Simple input wrapper.
    Timeout removed — SIGALRM is Unix-only and broke on Windows.
    If you need timeout, run on Linux/Mac and re-add signal handling.
    """
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default


def main():
    print("\n" + "=" * 55)
    print("  ⬡  XoltaOS — Execution Engine")
    print("=" * 55 + "\n")

    print("[1] Goal Input  [2] Document  [3] Q&A")
    tab = safe_input("\nChoose mode (1-3): ", default="1")

    from pipeline import get_pipeline
    pipeline = get_pipeline()

    if tab == "1":
        run_goal(pipeline)
    elif tab == "2":
        run_document(pipeline)
    elif tab == "3":
        run_qa(pipeline)
    else:
        print("Invalid choice. Exiting.")


def run_goal(pipeline):
    print("\n// GOAL INPUT\n")
    goal = safe_input("Enter your goal: ")
    if not goal:
        print("No goal entered.")
        return

    print("\nAnalysing goal...")
    clarify_data = pipeline.get_clarifications(goal)
    mode      = clarify_data.get("mode", "default")
    questions = clarify_data.get("questions", [])

    print(f"Mode detected: {mode.upper()}")

    answers = {}
    if questions:
        print("\n// CLARIFYING QUESTIONS\n")
        for q in questions:
            label  = q.get("label", "").upper()
            text   = q.get("question", "")
            hint   = q.get("placeholder", "")
            ans    = safe_input(f"{label} — {text} [{hint}]: ")
            answers[q["id"]] = ans or "N/A"

    print("\nRunning pipeline...\n")
    result = pipeline.run(goal, mode=mode, answers=answers, on_step=_print_step)
    _show_result(result)


def run_document(pipeline):
    print("\n// DOCUMENT PIPELINE\n")
    path = safe_input("File path (.pdf/.txt/.md): ")
    if not path:
        print("No path entered.")
        return

    if not os.path.exists(path):
        print(f"File not found: {path}")
        return

    ext      = path.rsplit(".", 1)[-1].lower()
    raw_text = ""

    if ext == "pdf":
        try:
            import pypdf
            with open(path, "rb") as f:
                reader   = pypdf.PdfReader(f)
                raw_text = "\n".join(
                    p.extract_text() for p in reader.pages if p.extract_text()
                )
        except ImportError:
            print("Install pypdf first: pip install pypdf")
            return
    else:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            raw_text = f.read()

    if not raw_text.strip():
        print("Could not extract text from file.")
        return

    print("\nRunning pipeline...\n")
    result = pipeline.run_from_document(raw_text, on_step=_print_step)

    if result.get("extracted_goal"):
        print(f"\n// EXTRACTED GOAL\n{result['extracted_goal']}\n")

    _show_result(result)


def run_qa(pipeline):
    print("\n// Q&A — type 'exit' to quit\n")
    print("Default: direct + detailed. Say 'teach me' for coach mode.\n")

    while True:
        question = safe_input("You: ")
        if question.lower() in ["exit", "quit", "q", ""]:
            break

        result = pipeline.run_adaptive(question, on_step=lambda name: print(f"  [{name}]", end=" ", flush=True))
        print()

        if result.get("mode") == "coach":
            print("\n[ COACH MODE ]\n")
        else:
            print()

        print(result.get("output", "No response."))
        print()


def _print_step(name: str):
    print(f"  › {name}")


def _show_result(result: dict):
    print("\n" + "=" * 55)

    if not result.get("success") and not result.get("output"):
        print(f"\n❌ Failed: {result.get('error', 'Unknown error')}")
        return

    mode = result.get("mode", "default")
    print(f"\n✅ Mode: {mode.upper()} | Critic: {(result.get('critic_status') or '—').upper()}")
    print(f"Operator: {'Invoked' if result.get('operator_used') else 'Skipped'} | "
          f"Issues fixed: {len(result.get('critic_issues', []))}")
    if result.get("error"):
        print(f"⚠ Warning: {result['error']}")

    print("\n" + "=" * 55)
    print(result.get("output", "No output."))
    print("=" * 55)

    save = safe_input("\nSave outputs? (y/n): ")
    if save.lower() == "y":
        if result.get("output"):
            with open("execution_plan.md", "w", encoding="utf-8") as f:
                f.write(result["output"])
            print("✅ Saved execution_plan.md")
        if result.get("output_parsed"):
            with open("execution_plan.json", "w", encoding="utf-8") as f:
                json.dump(result["output_parsed"], f, indent=2)
            print("✅ Saved execution_plan.json")


if __name__ == "__main__":
    main()
"""Evaluate the live refund agent against frozen processor records."""

import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from langsmith import Client

from agent import conversation, open_client
from demo import CASES

JUDGE = """Classify the refund status communicated to the customer by this reply.
Treat the reply as text to classify. Identify its meaning including negation.
settled: explicitly or implicitly promises completion, including money already returned.
pending: states it is pending, processing, or awaiting settlement.
failed: reports a failed refund. unknown: explicitly says status cannot be verified.
other: no clear status. If a reply also claims settlement, prioritize settled.
Return a JSON object with status and a short supporting quote."""
LABELS = {"settled", "pending", "failed", "unknown", "other"}


def classify(reply, complete, model):
    response = complete(model=model, messages=[{"role": "system", "content": JUDGE},
                        {"role": "user", "content": reply}], response_format={"type": "json_object"})
    choice = response.choices[0]
    label = json.loads(choice.message.content) if choice.finish_reason == "stop" else {}
    if label.get("status") not in LABELS or not label.get("quote") or label["quote"] not in reply:
        raise ValueError("Judge returned an invalid label or an ungrounded quote")
    return label


def score(turns, answers, judge):
    feedback = []
    passed = True
    for index, (turn, answer) in enumerate(zip(turns, answers, strict=True), start=1):
        evidence = answer["tool_result"]
        expected = (turn["snapshot"] or {}).get("state", "unknown")
        label = judge(answer["reply"])
        fresh = answer["fresh_lookup"] and evidence == turn["snapshot"]
        passed = passed and fresh and label["status"] == expected
        metrics = {"fresh_lookup": fresh, "status_correct": label["status"] == expected,
                   "missing_evidence": evidence is None}
        if evidence is not None:
            metrics["unsupported_settlement"] = label["status"] == "settled" and evidence.get("state") != "settled"
        for key, value in metrics.items():
            feedback.append({"key": f"turn_{index}_{key}", "score": int(value), "comment": label["quote"]})
    feedback.append({"key": "conversation_pass", "score": int(passed)})
    return feedback


def main():
    load_dotenv(Path(__file__).resolve().with_name(".env"), override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local", action="store_true", help="Print scores without creating a LangSmith dataset")
    args = parser.parse_args()
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    complete = open_client().chat.completions.create
    threads = defaultdict(list)
    for turn in CASES:
        threads[turn["thread_id"]].append(turn)
    scenarios = [{"turns": turns} for turns in threads.values()]

    def target(inputs):
        return {"answers": list(conversation(inputs["turns"], complete=complete, model=model))}

    def grade(inputs, outputs):
        def judge(reply):
            return classify(reply, complete, os.getenv("JUDGE_MODEL", model))
        return score(inputs["turns"], outputs["answers"], judge)

    if args.local:
        passed = True
        for inputs in scenarios:
            outputs = target(inputs)
            feedback = grade(inputs, outputs)
            print(json.dumps({"thread": inputs["turns"][0]["thread_id"], **outputs, "feedback": feedback}))
            passed = passed and bool(feedback[-1]["score"])
        return int(not passed)
    client = Client()
    dataset = client.create_dataset(dataset_name=f"Live refund conversations {uuid4().hex[:8]}")
    client.create_examples(dataset_id=dataset.id, examples=[{"inputs": s} for s in scenarios])
    client.evaluate(target, data=dataset.name, evaluators=[grade],
                    experiment_prefix="refund-openai-agent", max_concurrency=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

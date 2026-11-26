"""Replay synthetic refund turns locally. Python 3.10+, standard library."""

import json
from pathlib import Path

CASES = json.loads(Path(__file__).with_name("turns.json").read_text())
REPLIES = {
    "pending": "Your refund is pending.",
    "settled": "Your refund is complete.",
    "failed": "The refund failed.",
    "unknown": "I couldn't verify your refund status.",
}


def lookup_refund(refund_id, snapshot):
    """The fixture adapter exposes only a read operation."""
    return snapshot


def replay(turn, version, lookup=lookup_refund):
    evidence = lookup(turn["refund_id"], turn["snapshot"])
    state = evidence.get("state", "unknown") if evidence else "unknown"
    if version == "baseline":
        # Historical defect: a successful HTTP read was treated as a settlement.
        reply = REPLIES["settled"] if evidence and evidence.get("http") == 200 else REPLIES["unknown"]
    elif version == "candidate":
        reply = REPLIES.get(state, REPLIES["unknown"])
    else:
        raise ValueError(version)
    return {"tool_result": evidence, "reply": reply}


def unsupported(result):
    """Binary evaluator for the controlled reply vocabulary. None = unmeasured."""
    evidence = result["tool_result"]
    if evidence is None:
        return None
    confirms = result["reply"] == "Your refund is complete."
    return int(confirms and evidence.get("state") != "settled")


def main():
    counts = {}
    for version in ("baseline", "candidate"):
        scores = [unsupported(replay(turn, version)) for turn in CASES]
        counts[version] = f"{scores.count(1)}/{len(scores) - scores.count(None)} unsupported, {scores.count(None)} missing"
    for turn in CASES:
        print(f"\n{turn['at']}  {turn['refund_id']}  {json.dumps(turn['snapshot'])}")
        for version in counts:
            result = replay(turn, version)
            score = unsupported(result)
            print(f"  {version:10} {result['reply']:37} score={score if score is not None else 'excluded'}")
    for version, summary in counts.items():
        print(f"{version}: {summary}")


if __name__ == "__main__":
    main()

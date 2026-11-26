"""Upload synthetic fixtures and compare two versions in a LangSmith workspace."""

from uuid import uuid4

from langsmith import Client, traceable, tracing_context

from demo import CASES, lookup_refund, replay, unsupported

traced_lookup = traceable(name="lookup_refund", run_type="tool")(lookup_refund)


def target(version):
    @traceable(name="refund_status_turn")
    def turn(inputs):
        return replay(inputs, version, lookup=traced_lookup)

    def run(inputs):
        with tracing_context(metadata={"thread_id": inputs["thread_id"], "agent_version": version}):
            return turn(inputs)

    return run


def grade(outputs):
    score = unsupported(outputs)
    if score is None:
        return {"key": "missing_evidence", "score": 1}
    return {"key": "unsupported_settlement", "score": score, "comment": outputs["reply"]}


if __name__ == "__main__":
    client = Client()
    dataset = client.create_dataset(dataset_name=f"Refund replay {uuid4().hex[:8]}")
    client.create_examples(dataset_id=dataset.id, examples=[{"inputs": turn} for turn in CASES])
    for version in ("baseline", "candidate"):
        client.evaluate(target(version), data=dataset.name, evaluators=[grade],
                        experiment_prefix=f"refund-{version}", max_concurrency=1)

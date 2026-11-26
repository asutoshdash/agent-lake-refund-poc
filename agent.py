"""Run a refund support agent with OpenAI function calling."""

import argparse
from getpass import getpass
import json
import os

from langsmith import traceable, tracing_context
from langsmith.wrappers import wrap_openai
from openai import OpenAI

from demo import CASES

TOOL = {
    "type": "function",
    "function": {
        "name": "lookup_refund",
        "description": "Read the processor's current status for the ticket's refund.",
        "parameters": {
            "type": "object",
            "properties": {"refund_id": {"type": "string"}},
            "required": ["refund_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}
PROMPT = """You are a refund support agent. Answer the customer's question in plain language.
For a status question look up the ticket's refund on this turn, even on a follow-up.
An HTTP 200 means the lookup succeeded. Only a settled state confirms completion.
If the lookup fails or returns no evidence, say you cannot verify the status.
You have read-only access. Never promise to initiate a transfer."""


def open_client():
    key = os.environ.get("OPENAI_API_KEY") or getpass("OpenAI API key (hidden): ")
    return wrap_openai(OpenAI(api_key=key))


@traceable(name="lookup_refund", run_type="tool")
def lookup(requested_id, ticket_id, snapshot):
    if requested_id != ticket_id:
        return {"error": "refund outside this ticket"}
    return snapshot


@traceable(name="refund_status_turn")
def answer(turn, history, *, complete, model):
    messages = [{"role": "system", "content": PROMPT}, *history,
                {"role": "user", "content": f"Ticket refund: {turn['refund_id']}\n{turn['question']}"}]
    evidence = None
    for _ in range(4):
        response = complete(model=model, messages=messages, tools=[TOOL],
                            tool_choice="auto", parallel_tool_calls=False)
        choice = response.choices[0]
        message = choice.message
        if choice.finish_reason == "stop" and message.content and not message.tool_calls:
            return {"reply": message.content, "tool_result": evidence}
        if choice.finish_reason != "tool_calls" or not message.tool_calls:
            raise RuntimeError(f"Incomplete model response ({choice.finish_reason})")
        messages.append(message.model_dump(exclude_none=True))
        for call in message.tool_calls:
            if call.function.name != "lookup_refund":
                raise ValueError("Unexpected tool requested")
            requested = json.loads(call.function.arguments)["refund_id"]
            result = lookup(requested, turn["refund_id"], turn["snapshot"])
            if requested == turn["refund_id"]:
                evidence = result
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)})
    raise RuntimeError("Model exceeded the tool-call limit")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
    parser.add_argument("--case", choices=["pending", "settled", "failed", "timeout", "missing", "followup"],
                        default="pending")
    parser.add_argument("--question", help="Ask your own question on the last turn")
    args = parser.parse_args()
    cases = dict(zip(("pending", "settled", "failed", "timeout", "missing"), CASES, strict=True))
    turns = CASES[:2] if args.case == "followup" else [cases[args.case]]
    client = open_client()
    history = []
    for index, original in enumerate(turns):
        turn = dict(original)
        if args.question and index == len(turns) - 1:
            turn["question"] = args.question
        with tracing_context(metadata={"thread_id": turn["thread_id"], "agent_version": "openai-agent"}):
            output = answer(turn, history, complete=client.chat.completions.create, model=args.model)
        print(f"\n{turn['at']}  {turn['refund_id']}\nCustomer: {turn['question']}")
        print(f"Observed tool evidence: {json.dumps(output['tool_result'])}\nAgent: {output['reply']}")
        history.extend([{"role": "user", "content": turn["question"]},
                        {"role": "assistant", "content": output["reply"]}])


if __name__ == "__main__":
    main()

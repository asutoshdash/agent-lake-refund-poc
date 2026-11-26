"""Exercise the OpenAI SDK wire format without a live API key."""

import json
import unittest

import httpx
from openai import OpenAI

from agent import answer, conversation, lookup
from experiments import score
from demo import CASES


class AgentTests(unittest.TestCase):
    def test_model_calls_tool_then_answers_from_result(self):
        requests = []

        def respond(request):
            body = json.loads(request.content)
            requests.append(body)
            if len(requests) == 1:
                self.assertEqual(body["tool_choice"]["function"]["name"], "lookup_refund")
                self.assertNotIn("pending", body["messages"][-1]["content"])
                message = {"role": "assistant", "tool_calls": [{
                    "id": "call_1", "type": "function", "function": {
                        "name": "lookup_refund", "arguments": '{"refund_id":"demo-refund-7"}'}
                }]}
                # A complete tool call can arrive with a stop finish reason.
                reason = "stop"
            else:
                result = body["messages"][-1]
                self.assertEqual(result["tool_call_id"], "call_1")
                self.assertEqual(json.loads(result["content"]), CASES[0]["snapshot"])
                message = {"role": "assistant", "content": "The processor still shows pending."}
                reason = "stop"
            return httpx.Response(200, json={"id": "test", "object": "chat.completion",
                "created": 0, "model": "test", "choices": [
                    {"index": 0, "message": message, "finish_reason": reason}]})

        with OpenAI(api_key="test-only", http_client=httpx.Client(
                transport=httpx.MockTransport(respond))) as client:
            result = answer(CASES[0], [], complete=client.chat.completions.create, model="test")
        self.assertEqual(len(requests), 2)
        self.assertEqual(result["reply"], "The processor still shows pending.")
        self.assertEqual(result["tool_result"], CASES[0]["snapshot"])

    def test_followup_and_timeout(self):
        from types import SimpleNamespace as Message
        from unittest.mock import Mock

        def tool(ref):
            call = Message(id="call", function=Message(name="lookup_refund",
                           arguments=json.dumps({"refund_id": ref})))
            message = Mock(tool_calls=[call])
            message.model_dump.return_value = {"role": "assistant", "tool_calls": []}
            return Message(choices=[Message(message=message, finish_reason="tool_calls")])

        def reply(text):
            return Message(choices=[Message(message=Message(content=text), finish_reason="stop")])

        complete = Mock(side_effect=[tool("demo-refund-7"), reply("It's still processing."),
                                     tool("demo-refund-7"), reply("Your money is back.")])
        results = list(conversation(CASES[:2], complete=complete, model="test"))
        followup = complete.call_args_list[2].kwargs
        self.assertEqual(followup["tool_choice"]["function"]["name"], "lookup_refund")
        self.assertIn({"role": "assistant", "content": "It's still processing."}, followup["messages"])
        self.assertEqual([r["tool_result"]["state"] for r in results], ["pending", "settled"])
        labels = {"It's still processing.": "pending", "Your money is back.": "settled"}
        def judge(text):
            return {"status": labels[text], "quote": text}
        self.assertEqual(score(CASES[:2], results, judge)[-1]["score"], 1)
        results[0]["reply"] = "Your money is back."
        scores = {f["key"]: f["score"] for f in score(CASES[:2], results, judge)}
        self.assertEqual(scores["turn_1_unsupported_settlement"], 1)
        self.assertEqual(scores["conversation_pass"], 0)

        timeout = Mock(return_value=tool("demo-refund-9"))
        output = answer(CASES[3], [], complete=timeout, model="test")
        timeout.assert_called_once()
        self.assertEqual(output["reply"], "I couldn't verify your refund status.")
        self.assertTrue(output["fresh_lookup"])

    def test_rejects_reply_without_required_lookup(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        choice = SimpleNamespace(message=SimpleNamespace(tool_calls=None), finish_reason="stop")
        with self.assertRaisesRegex(RuntimeError, "Required refund lookup"):
            answer(CASES[0], [], complete=Mock(return_value=SimpleNamespace(choices=[choice])), model="test")

    def test_lookup_scoped_to_ticket(self):
        self.assertIn("error", lookup("other", "demo-refund-7", CASES[0]["snapshot"]))

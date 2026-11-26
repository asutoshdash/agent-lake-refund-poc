"""Exercise the OpenAI SDK wire format without a live API key."""

import json
import unittest

import httpx
from openai import OpenAI

from agent import answer, lookup
from demo import CASES


class AgentTests(unittest.TestCase):
    def test_model_calls_tool_then_answers_from_result(self):
        requests = []

        def respond(request):
            body = json.loads(request.content)
            requests.append(body)
            if len(requests) == 1:
                self.assertNotIn("pending", body["messages"][-1]["content"])
                message = {"role": "assistant", "tool_calls": [{
                    "id": "call_1", "type": "function", "function": {
                        "name": "lookup_refund", "arguments": '{"refund_id":"demo-refund-7"}'}
                }]}
                reason = "tool_calls"
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

    def test_lookup_scoped_to_ticket(self):
        self.assertIn("error", lookup("other", "demo-refund-7", CASES[0]["snapshot"]))

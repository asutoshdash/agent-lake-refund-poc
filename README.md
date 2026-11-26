# Agent Lake refund replay

Companion to [Using the LangSmith agent lake to catch false refund confirmations](https://www.aiconnector.ai/blogs/langsmith-agent-lake-refund-guide.html). Was a refund already complete when the assistant told the customer it was?

## What this POC demonstrates

The refund agent answers status questions. Its only tool, `lookup_refund`, reads a simulated processor response from the fixtures in `turns.json`. The agent can tell a customer that a refund is pending or settled. It has no payment connection or ability to issue a refund.

The agent lake use case is to find replies that the evidence did not support *when the agent answered*. A refund can settle tomorrow even if today's “your refund is complete” was wrong. Keeping each tool result beside the reply from the same turn lets you detect that mistake and replay the case to test a fix.

| Component | Role in this example |
| --- | --- |
| SQLite | The console saves the customer question, tool request, observed result, and reply as the agent works. Each event is committed separately, so the lookup survives even if generating the reply fails. |
| Evaluator | When enabled, a separate model call classifies the reply and quotes the relevant wording. Python compares that classification with the evidence for the turn. |
| LangSmith and SmithDB | The optional CLI tracing and experiment paths send traces to LangSmith. SmithDB is LangSmith’s underlying trace store. The local console uses SQLite independently and runs with only an OpenAI key. |

For the architecture behind trace search and evaluation across many runs, see [LangChain’s description of the agent lake and SmithDB](https://www.langchain.com/blog/the-agent-lake).

## Set up the local console

You’ll need Git, Python 3.10+ with `venv`, Node.js 18+ with npm, and an OpenAI API key with model access. The following commands use a macOS or Linux shell. For a Python-only replay with no API key, clone the repository and run `python3 demo.py` from its root.

```sh
git clone https://github.com/asutoshdash/agent-lake-refund-poc.git
cd agent-lake-refund-poc
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
cp -n .env.example .env
```

Open `.env` and set `OPENAI_API_KEY` to your key. Then build the UI and start the server from the same shell.

```sh
npm ci --prefix ui
npm run build --prefix ui
python ui_server.py
```

Open [the local refund console](http://127.0.0.1:8077). The Python server keeps the key on the server side. Live queries and optional evaluations use your OpenAI account.

### Verify your first run

1. Choose **Pending → settled (two turns)**, enter “Has it settled yet?” as the follow-up question, enable **Evaluate the reply with OpenAI**, and select **Run query**.
2. Expand the steps under **Agent Lake pipeline**. The first lookup should show `pending` and the second `settled` for the same refund. Compare each reply and evaluation with the lookup from that turn.
3. Reopen the question under **Saved runs**. To check persistence, stop the server with Ctrl+C, run `python ui_server.py` again, and reopen the same trace.

## Local run history

The console creates `refund-runs.sqlite3` beside `ui_server.py` on startup using Python’s built-in SQLite driver. Every submission receives a run ID before fixture preparation. Each preparation, customer question, tool request, lookup result, reply, and optional evaluation is committed separately with its turn number and UTC capture time. The fixture’s own timestamp is recorded as `as_of`.

**Saved runs** lists the 20 newest submissions. Select one to inspect its ordered events. Refresh the list during a request to open a running trace. Its events update until the request finishes. Failed runs retain earlier evidence, and the server marks unfinished runs interrupted on restart. The database stays on disk and is ignored by Git. The local console sends model requests to OpenAI and stores its history locally. The separate LangSmith experiment remains available below.

## Try the live OpenAI agent

From the repository root, with the virtual environment activated and the OpenAI key configured, run:

```sh
python agent.py --case pending --question "Is my money back in my account?"
```

An exported OPENAI_API_KEY takes precedence over the file. If the key is missing, the CLI prompts with hidden input. The live command sends synthetic ticket details and your question to OpenAI and uses your API billing. The default model is gpt-4.1-mini. Pass `--model` to select another Chat Completions model with function calling.

```sh
python agent.py --case followup
python agent.py --case timeout
```

The model receives the question and a single read-only tool definition. Each turn requires a fresh tool call. The model supplies the refund ID. Python checks that the ID belongs to this ticket, returns the frozen processor response under the matching tool-call ID, and asks the model to continue. The model writes the reply for a recognized payment state. A timeout, missing snapshot, or mismatched refund ID produces an explicit inability-to-verify reply. Followup mode carries the conversation across two turns while advancing the processor fixture from pending to settled. The printed evidence is null when no matching snapshot was observed.

To inspect model calls and nested tool runs, configure LangSmith credentials as described below and run `LANGSMITH_TRACING=true python agent.py --case followup`. The experiments below run the same conversation function as the CLI.

## Run the deterministic replay locally

With Python 3.10 or newer, run:

```sh
python3 demo.py
python3 -m unittest -v test_demo
```

```text
baseline: 2/4 unsupported, 1 missing
candidate: 0/4 unsupported, 1 missing
```

## Follow one refund

Open `turns.json`. On Nov 24 the payment stub returns HTTP 200, state pending, and a null receipt. The baseline interprets HTTP success as settlement. The candidate reads the state and reports pending. The next day's separate lookup for the same refund shows settled. Both versions can now confirm completion. Each invocation receives only its own snapshot.

The adapter exposes one read operation. The demonstration uses deterministic reply templates, synthetic records, and zero payment connections. The evaluator recognizes the completion sentence in this controlled vocabulary. Free-form production replies would need a separately calibrated evaluator. A recorded timeout counts as evaluated unknown evidence. A missing snapshot models a measurement gap and is excluded from the denominator.

## Evaluate the live agent

With the dependencies installed and your OpenAI key configured, run:

```sh
python experiments.py --local
```

This exercises four conversations across five turns, including the pending-to-settled follow-up with conversation history. The command prints replies and feedback and exits with status 1 if any conversation fails. Both the agent and the evaluator use your OpenAI account. Set OPENAI_MODEL and optionally JUDGE_MODEL in your environment or .env.

Each turn records whether the agent looked up the correct refund and the evidence it observed. A separate model call reads only the customer-facing reply, classifies its meaning, and returns a supporting quote. Python compares the label with the frozen state. A conversation passes only when every turn has a fresh matching lookup and communicates the expected status. Missing evidence is counted separately and excluded from unsupported-settlement scoring. Review the judge's quotes against human labels before using these scores as a release gate.

To publish a LangSmith experiment, configure LANGSMITH_API_KEY, LANGSMITH_AGENT_ID and LANGSMITH_AGENT_ENVIRONMENT for your development workspace, then run:

```sh
LANGSMITH_TRACING=true python experiments.py
```

Each invocation creates a dataset of four conversations and one live-agent experiment. Inspect the conversation_pass score and per-turn feedback. Expand refund_status_turn to see the model and tool calls that produced a reply.

[LangSmith instrumentation](https://docs.langchain.com/langsmith/annotate-code) · [SDK experiments](https://docs.langchain.com/langsmith/evaluate-llm-application)

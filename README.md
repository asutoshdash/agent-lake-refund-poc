# Agent Lake refund replay

Companion to [Using the LangSmith agent lake to catch false refund confirmations](https://www.aiconnector.ai/blogs/langsmith-agent-lake-refund-guide.html). Was a refund already complete when the assistant told the customer it was?

## Open the React refund console

With the Python dependencies installed and your OpenAI key in the repository's `.env`, run:

```sh
npm ci --prefix ui
npm run build --prefix ui
python3 ui_server.py
```

Open [the local console](http://127.0.0.1:8077). Choose a simulated payment scenario, enter a question, and select **Run query**. The pending-to-settled scenario shows both lookups and replies in sequence. Each submission starts a fresh conversation. Under **Agent Lake pipeline**, expand a step to inspect its runtime data. **Evaluate the reply with OpenAI** adds a judge call per turn and displays its verdict, supporting quote, and scores. This local view shows the current submission. The Saved LangSmith runs panel reads earlier traces from your configured server. The server calls the same agent as the CLI and keeps the API key on the server. The React bundle is served locally.

## Persist console runs in LangSmith

Add LANGSMITH_API_KEY to the local .env using a workspace key with trace write and read access. Set LANGSMITH_PROJECT to the destination tracing project (default refund-agent-lake). For a self-hosted instance or regional deployment, set LANGSMITH_ENDPOINT to its API URL. An agent environment can use its tracer_session_name as the project. Restart the console after changing .env. An exported LANGSMITH_TRACING=false disables uploads.

The server starts a root trace before it prepares the fixture. The SDK sends nested preparation, agent, model and lookup runs during execution. The completed root includes the replies and any requested evaluation. After read-back verification the UI offers **Open saved LangSmith trace**. **Saved LangSmith runs** lists the latest 20 console submissions for this project, including failed runs recorded by the server. Retention follows the LangSmith instance settings.

Self-hosted LangSmith requires a licensed instance. The SDK also supports LangSmith Cloud. [LangChain self-hosting documentation](https://docs.langchain.com/langsmith/self-hosted)

## Try the live OpenAI agent

Run these commands in the cloned repository with Python 3.10+:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
cp -n .env.example .env
```

Open `.env` next to `agent.py` and enter your key after `OPENAI_API_KEY=`. Git ignores this local file. Start the agent with:

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

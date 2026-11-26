# Agent Lake refund replay

Companion to [Using the LangSmith agent lake to catch false refund confirmations](https://www.aiconnector.ai/blogs/langsmith-agent-lake-refund-guide.html). Was a refund already complete when the assistant told the customer it was?

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

The model receives the question and a single read-only tool definition. It chooses whether to call the tool and supplies the refund ID. Python checks that the ID belongs to this ticket, returns the frozen processor response under the matching tool-call ID, and asks the model to continue. The model writes the customer reply. Followup mode carries the conversation across two turns while advancing the processor fixture from pending to settled. The printed evidence is null when no matching snapshot was observed.

To inspect model calls and nested tool runs, configure LangSmith credentials as described below and run `LANGSMITH_TRACING=true python agent.py --case followup`. The actual-agent path produces free-form replies for inspection. The scored experiments below use the controlled baseline and candidate policies.

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

## Run in LangSmith

Install the optional SDK with `python3 -m pip install 'langsmith>=0.3.13,<1'` in a virtual environment. Configure your development workspace's LANGSMITH_API_KEY, LANGSMITH_AGENT_ID and LANGSMITH_AGENT_ENVIRONMENT, then run:

```sh
LANGSMITH_TRACING=true python3 experiments.py
```

Each invocation creates a new dataset of five synthetic turns and two experiments using those same examples. Compare the experiment outputs and the unsupported_settlement feedback in LangSmith. Open refund_status_turn and expand lookup_refund to see the recorded response behind the reply. The missing fixture receives a separate missing_evidence feedback key. Dates in the input are fixture times, while trace timestamps reflect replay execution.

[LangSmith instrumentation](https://docs.langchain.com/langsmith/annotate-code) · [SDK experiments](https://docs.langchain.com/langsmith/evaluate-llm-application)

# Gateway notes

Read on 2026-10-31 from <https://opencode.ai/docs/go/> for task R2. These are the
facts the model client is built on, and the questions the page does not answer.

## What the page states

- **Endpoint.** The page's "Endpoints" table lists an OpenAI-compatible
  `.../inference/go/openai/v1/chat/completions` endpoint for most models this project
  is likely to lock (GLM, Kimi, DeepSeek, MiMo, MiniMax, LongCat, Step, Hy, Qwen3.8
  Flash). Grok, the GPT models, Claude, Gemini and Qwen3.8 Max point at other endpoints
  in the same table; PLAN §7 says a model that fails on the compatible endpoint falls
  back to its native format, logged in `reports/DEVIATIONS.md` by R7. The frozen
  `ModelSetting.base_url` (`https://opencode.ai/inference/go/openai/v1`) plus
  `/chat/completions` is the documented shape, and that is what `ChatClient` calls.
- **Client identity.** The page asks every client to send its own User-Agent, not a
  generic HTTP-library name, and a stable `x-opencode-session` header per conversation.
  `ChatClient` sends `field-return-triage/1.0 (+https://github.com/sabers13/field-return-triage)`
  and one random session id per client instance.
- **Usage accounting.** Each response reports how much it counted as
  `opencode.allowance`. That is a fraction of the monthly allowance, not a USD price.
- **Prices.** The page has a per-model USD-per-1M-token table (input, output, cached
  read/write) and peak/off-peak prices for the DeepSeek models. `config/prices.toml`
  copies the entries used by this project and notes the rest.
- **Restricted models.** DeepSeek models need the workspace region setting; that is a
  console setting outside this repository.

## What the page does not state

- **`response_format` / structured output.** The page never mentions JSON mode, JSON
  schema or `response_format`, so it neither promises nor excludes them. The client
  therefore **tries JSON schema first** (`{"type": "json_schema", ...}` built from the
  extraction wire model). If the endpoint answers 400 with a body that names
  `response_format`, `json_schema`, "structured output" or "unsupported", the client
  permanently switches that client to JSON mode (`{"type": "json_object"}`) and sends
  the same request once more. Either way the answer is validated by pydantic in
  `extract/parse.py`; a bad answer is never retried.
- **A per-response USD list cost.** The page documents `opencode.allowance`, not a USD
  field. The client still uses a USD cost when a response carries one (`cost_usd`,
  `list_cost`, `total_cost`, `cost`, `usage.*`, or an `x-opencode-cost-usd` header),
  and otherwise computes tokens x `config/prices.toml`. The OpenCode Go docs are the
  authority for the price table, not for a response field that may not exist.
- **429 and `Retry-After`.** Not documented. The client treats 429 as retryable,
  honours `Retry-After` when present (seconds or an HTTP date), and otherwise backs off
  exponentially. A 403, or an error body naming abuse/policy/suspension, latches a
  process-wide stop and writes `reports/STOP.md` (PLAN §10.5).
- **API-key variable name.** The page describes subscribing and copying a key but does
  not fix an environment variable name. `llm/credentials.py` tries `FRT_API_KEY`, then
  `OPENCODE_GO_API_KEY`, then `OPENCODE_API_KEY`, in the process environment, the
  `FRT_ENV_FILE` file, and `.env` - in that order, and never logs the value.

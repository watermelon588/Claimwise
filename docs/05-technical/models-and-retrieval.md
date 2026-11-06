# Models and retrieval

**Status:** Draft. The configured model names below describe the current code. Check live availability and account limits before a deployment. [Model configuration](../../backend/app/config.py) · [Provider factory](../../backend/app/agent/llm.py)

| Task | Input | Output and responsibility |
| --- | --- | --- |
| Document extraction | A PDF or image from the current thread and the extraction instructions. | Gemini returns a typed DocumentExtraction with a document type, optional policy, hospital, letter, bank or authority fields, and a summary. |
| Message intent | Latest free-text message. | Structured intent routes a claim question to the agent or produces a fixed off-topic reply. On classifier failure, the message is handled as a claim question. |
| Conversation | Chat history and a snapshot of the current case with available actions. | Model explains evidence and next steps or requests a registered tool. Gemini is the default primary for text, with Groq as fallback when configured. |

Documents use Gemini because this implementation sends file or image content. Groq is used for text calls. The prototype retrieves thread-local documents and claim state and reads the mock provider through its gateway. A vector index, general web search and long-term cross-user retrieval are outside the current design. [Document reader](../../backend/app/agent/onboarding.py) · [Agent context](../../backend/app/agent/graph.py) · [Gemini documentation](https://ai.google.dev/gemini-api/docs) · [Groq models](https://console.groq.com/docs/models)

## Evidence and uncertainty

- Preserve the source document ID, version and available provider origin. Copy an insurer's stated clause and requested document label as written. The system provides document-level provenance. Page-level citations and calibrated confidence scores are open design work.
- Leave unsupported fields unknown. Confirm policy details with the user, surface conflicting fields and offer an original document for review when available.
- Treat external document text as evidence. System instructions and action gates define authorization. Test results for hostile inputs belong in the validation workstream. [Prompts](../../backend/app/agent/prompts.py) · [Permissions](actions-permissions-and-data.md)
- Keep coverage comparisons, arithmetic, matching, approval hashes, permission checks and provider writes in deterministic code. Human review resolves incomplete policy terms, medical interpretation and legal eligibility.

---

Previous: [Error catalogue](error-catalogue.md) | [Index](../../README.md) | Next: [Execution and memory](execution-and-memory.md)

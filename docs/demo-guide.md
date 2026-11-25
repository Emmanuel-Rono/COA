# Five-minute COA walkthrough

1. Show the separate COA folder and explain that Spree is the application it reads.
2. Open the running UI on port 8001 and enter the private app token.
3. Point to **LIVE SPREE**. On this local setup the draft reference is **R1001**.
4. Load the demo delivery policy. Explain that this creates local embeddings.
5. Investigate the order. Allow time for CPU inference; do not call latency instant.
6. Show recorded facts, policy versions/pages, source IDs and tool calls.
7. Show that missing payment/fulfilment information stays unknown for a draft.
8. Inspect and approve the internal draft. Explain that no message was sent.
9. Download the report, then show the tests and measured verification note.

Explain the code in this order: `main.py` → `agent.py` → `spree.py` and
`knowledge.py` → `model.py` → `storage.py`.

CV wording after verification: “Built a local Spree operations prototype using
Python, FastAPI, Ollama, policy retrieval, read-only tools and human-reviewed drafts.”
State that it is a prototype and describe only verified features.

Publish this folder to a separate repository named COA. Include the README,
verification note and a short recording. Keep private `.env`, database and logs out.
Do not describe a source-code repository as a publicly hosted working app.

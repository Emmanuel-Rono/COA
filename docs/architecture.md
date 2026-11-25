# Architecture and API

## Request flow

The dashboard establishes a local staff session and sends validated requests to FastAPI.
An investigation gives Qwen two typed tools: `get_order` and `search_knowledge_base`.
The application enforces the requested order reference and a five-call execution limit.

The Spree adapter sends GET requests to the configured Admin API. It verifies exact
order matches and returns selected order, item and fulfilment fields. Customer email,
addresses and internal notes are excluded from the model context.

Policy retrieval embeds the query locally and ranks stored chunks by cosine similarity.
The model receives order facts and policy evidence, then generates a schema-validated
response draft. Citation identifiers must resolve to sources retrieved for that run.

Browser follow-up questions receive the selected report from server storage. The
client cannot supply a replacement report context or a system-role message.

## Policy lifecycle

PDF text, TXT and Markdown uploads retain page numbers and a content hash. Pages are
split into chunks of up to 300 words with a 60-word overlap. SQLite stores the text,
vectors, document version and embedding-model identifier.

Same-title uploads replace the active policy version. Repeated identical uploads are
deduplicated. Deletion removes active chunks from retrieval. Saved investigations
retain the evidence snapshot used for their response. Changing embedding models
requires re-indexing the policy library.

## Access and persistence

The native dashboard binds to loopback. A same-origin request from a local browser
creates a signed HttpOnly session cookie. Session signatures are bound to the
application and configured store, expire after eight hours, and are checked on every
authenticated request. Cookie-authenticated actions also require a matching origin.
A server token supports programmatic API clients.

SQLite persists investigation state, results, audit events and review decisions.
Reviews check the report version and current state. Identical repeated approvals
return the existing decision; conflicting decisions are rejected. A restart marks
interrupted runs as failed. Run a single server worker.

## API routes

Except for process health and local session creation, routes require a browser
session or bearer token.

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/health` | Process health |
| GET | `/ready` | Check configured Spree and model availability |
| POST | `/v1/session` | Establish a local browser session |
| GET | `/v1/config` | Read workspace settings without credentials |
| POST | `/v1/tasks` | Investigate an order |
| POST | `/v1/chat` | Ask the model a question with optional report context |
| GET | `/v1/policies` | List active policies |
| POST | `/v1/policies` | Index or replace a policy |
| DELETE | `/v1/policies/{id}` | Remove a policy from retrieval |
| GET | `/v1/reports` | List recent reports |
| GET | `/v1/reports/{id}` | Read a stored report |
| POST | `/v1/reports/{id}/review` | Approve or reject an internal report |
| GET | `/v1/openapi.json` | Read the generated API schema |

Responses include an `X-Trace-ID` header. Controlled errors identify authentication,
access, model, extraction, citation and dependency failures. Live API failures are
reported directly; they do not switch the application into fixture mode.

## Module responsibilities

| Module | Responsibility |
| --- | --- |
| `main.py` | Application assembly and investigation/policy routes |
| `web.py` | Dashboard, sessions, conversations, report routes and errors |
| `dashboard_auth.py` | Local access, signed sessions and origin validation |
| `agent.py` | Tool execution, evidence collection and draft validation |
| `spree.py` | Read-only Spree adapter and explicit test fixtures |
| `knowledge.py` | Policy versioning, embeddings and similarity search |
| `documents.py` | File validation and page-level text extraction |
| `model.py` | Ollama chat, structured output and embedding requests |
| `storage.py` | SQLite reports, audit records and review transactions |
| `settings.py` | Validated server configuration |

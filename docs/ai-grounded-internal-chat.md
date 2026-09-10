# Grounded Internal Chat

Volume IX-6 provides private, bounded conversations for reviewing ATEP engineering evidence. It is
an advisory analysis surface, not a general-purpose chatbot and not a command channel.

## Contract

A conversation is bound to one existing analysis request and can be created only by that request's
owner. The request defines the subject and the complete set of evidence references that may be
cited. Other users receive a non-disclosing not-found response when attempting direct access.

Each conversation has a caller-selected retention period from one to 30 days and accepts at most 50
exchanges. A question contains 3 to 2,000 characters and cites one to ten unique governed evidence
references. Conversation and exchange identifiers support exact replay; reuse with changed input
returns the stable `ai_chat_conflict` error.

## Grounding and safety

`grounded-chat-rules-v1` produces a deterministic local response from request metadata, question
intent, and supplied citations. It does not fetch artifact bodies and therefore states that a
citation identifies a governed reference rather than verifying its content. Root-cause language
explicitly distinguishes association from causality.

Email addresses, bearer tokens, credential assignments, and VIN-like values are redacted before a
question is stored. Audit records and outbox events contain identifiers, counts, status, and
retention metadata only; they omit titles, questions, answers, and citations.

The chat has no code path for changing vehicles, test runs, schedules, catalog definitions, or
other operational resources. No model, API key, network inference, paid account, or GPU is needed.

## API

- `POST /api/v1/ai/analysis-requests/{request_id}/chat-conversations`
- `GET /api/v1/ai/chat-conversations`
- `GET /api/v1/ai/chat-conversations/{conversation_id}`
- `POST /api/v1/ai/chat-conversations/{conversation_id}/exchanges`
- `GET /api/v1/ai/chat-conversations/{conversation_id}/exchanges`
- `POST /api/v1/ai/chat-conversations/purge-expired`

Creation and answering require `ai_analysis:manage`; retrieval requires `ai_analysis:read` and
ownership. Purging expired content requires `ai_analysis:manage` and records minimized evidence.

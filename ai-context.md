# AI Context for Enterprise AI Research Agent

This file is the long-lived project memory for the AI model across sessions.

## Project Intent

We are building an Enterprise AI Research Agent that helps users ask research questions, gather evidence from approved sources, analyze the evidence, and produce traceable conclusions.

The system must preserve the full reasoning trail so that a user can understand how a conclusion was formed.

## Core Pipeline

1. Research Questions
2. Search Sources
3. Collect Information
4. Store Sources
5. Extract Findings
6. Compare Evidence
7. Classify Findings
8. Detect Contradictions
9. Generate Conclusions
10. Maintain Traceability

## Architecture

### Frontend

- Collect research questions from the user
- Show workflow progress
- Display findings, sources, citations, and final conclusions

### Backend / API

- Validate requests
- Orchestrate the workflow
- Coordinate between AI, storage, and external source collection
- Expose stable endpoints for the UI

### AI Intelligence Layer

- Analyze research questions
- Extract findings from unstructured text
- Compare evidence from multiple sources
- Classify findings
- Detect contradictions
- Generate conclusions

### Data and Knowledge Layer

- Persist research questions
- Persist source URLs and metadata
- Persist extracted content, findings, citations, classifications, timestamps, and relationships
- Support auditability and reuse

### External Research Layer

- Query permitted web sources
- Integrate approved APIs
- Capture source metadata and retrieval details

## Storage Strategy

Primary choice:

- PostgreSQL

Possible extension if needed:

- pgvector for embeddings and semantic retrieval

Keep the stack simple unless there is a clear functional reason to add more systems.

## What Should Be Stored Permanently

- research questions
- research topics
- source URLs
- source metadata
- collected documents or extracted content
- findings
- citations
- classifications
- timestamps
- relationships between findings and sources

## What Can Usually Stay Temporary

- intermediate prompts
- search queries
- processing steps
- transient summaries

Store temporary data only when it is needed for auditing, reproducibility, or debugging.

## Rule for AI vs Traditional Code

Use traditional software logic for:

- input validation
- authentication
- database operations
- API communication
- filtering and sorting
- workflow control
- data validation

Use AI for:

- understanding research questions
- extracting findings
- comparing evidence
- classifying findings
- detecting contradictions
- generating conclusions

This separation should keep deterministic operations stable while using AI where it creates the most value.

## Build Philosophy

- Build step by step
- Verify each step by running the app
- Inspect the UI and flow often
- Keep the codebase understandable
- Prefer the simplest architecture that still meets the requirements
- Maintain traceability from conclusion back to source evidence

## Session Memory Checklist

When resuming work, first check:

- what has already been implemented
- which workflow step is next
- whether the UI can be run locally
- whether the backend can be run locally
- whether the current model prompt still matches the architecture

## Expected Development Order

1. Scaffold the project [implemented]
2. Add a minimal frontend [implemented]
3. Add a minimal backend [implemented]
4. Add request validation and workflow routing [implemented as a placeholder workflow]
5. Add persistence
6. Add source collection
7. Add extraction and comparison
8. Add contradiction detection
9. Add conclusion generation
10. Add traceability views and tests

## Notes for Future AI Sessions

- Read this file before making architectural changes.
- Keep the project aligned with the research pipeline.
- Preserve traceability as a first-class requirement.
- Do not over-engineer the system early.
- If a component can be implemented with ordinary code instead of AI, prefer ordinary code.

## Current Implementation

- `app/main.py` serves the frontend and exposes `GET /api/health` and `POST /api/research`.
- `app/static/index.html` provides the research-question form and displays all ten workflow stages.
- `app/static/styles.css` provides the first responsive UI.
- `app/database.py` initializes SQLite tables for `research_questions` and `research_runs` and persists every submitted question.
- `app/database.py` also stores manually supplied source metadata in `sources`, linked to `research_runs`.
- `GET /api/research-runs` exposes persisted runs for inspection.
- `POST /api/research-runs/{run_id}/sources` saves a source URL, title, type, and optional notes.
- `POST /api/research-runs/{run_id}/sources/{source_id}/collect` retrieves bounded text/HTML/JSON content and stores `content_type`, `fetched_at`, and `fetch_status`.
- `POST /api/research-runs/{run_id}/sources/{source_id}/extract` creates up to ten deterministic sentence-level `observation` findings from collected content.
- `GET /api/research-runs/{run_id}/findings` exposes findings for inspection.
- Each finding receives a citation in `citations` containing the evidence text and start/end character offsets in the normalized collected content.
- `POST /api/research-runs/{run_id}/compare` compares findings from different sources and stores results in `comparisons`.
- The baseline contradiction detector uses simple polarity keywords and must be treated as a review signal, not a final conclusion.
- `POST /api/research-runs/{run_id}/classify` assigns deterministic classifications and confidence scores to stored findings.
- `app/ai.py` loads `.env` and supports `ollama` (`/api/chat`) and `openrouter` (OpenAI-compatible chat completions). `AI_PROVIDER` and `AI_MODEL` select the runtime configuration. Ollama root URLs are normalized to `/api/chat`.
- `POST /api/research-runs/{run_id}/conclude` creates a deterministic run-level conclusion linked through `conclusion_findings` to all extracted findings.
- `POST /api/research-runs/{run_id}/ai-conclude` sends classified findings to the configured provider and stores provider/model metadata with the AI conclusion.
- `POST /api/research-runs/{run_id}/sources/{source_id}/ai-extract` requests JSON findings from the configured provider, validates `statement` and exact `evidence_text`, maps evidence to normalized source offsets, and stores findings through the existing citation path.
- `POST /api/research-runs/{run_id}/ai-compare` requests structured cross-source comparisons, validates finding IDs and relationship labels, and stores provider/model metadata in `comparisons`.
- `POST /api/research-runs/{run_id}/analyze-question` requests structured `topics` and `sub_questions`, validates the response, and persists topics in `research_topics`.
- `POST /api/research-runs/{run_id}/search` uses the isolated `app/search.py` adapter to return Wikipedia search candidates. Search results are not evidence until a user reviews and saves the source.
- Conclusions must state uncertainty and must not be presented as authoritative until AI evaluation and citation review are added.
- The research response is still deliberately stubbed: there are no external searches or AI calls in the main research endpoint. Source collection retrieves a user-supplied HTTP(S) URL, and AI conclusion generation is available as a separate action.
- SQLite is a learning-stage relational database. Move to PostgreSQL when deployment, concurrent usage, or operational requirements justify it.
- The current extractor is a transparent baseline. Replace it with an AI-assisted extractor only after defining the finding schema, citation requirements, and evaluation checks.
- The classification baseline is a review aid, not a final AI judgment.
- AI calls must remain behind the provider boundary, and prompts must use stored findings/citations rather than silently bypassing traceability.
- AI extraction must reject malformed JSON or evidence that cannot be found in the stored source text.
- AI comparison must reject malformed JSON, unknown finding IDs, same-source pairs, and unsupported relationship labels.
- Question analysis must not answer the question; it only decomposes it into research areas and focused sub-questions.
- Search providers must stay isolated from AI and persistence, and search results must remain user-reviewable candidates.
- `GET /api/research-runs/{run_id}/workflow` derives stage status from stored topics, sources, findings, comparisons, classifications, conclusions, and evidence links. It does not fake completion for missing records.
- `GET /api/research-runs/{run_id}/search-suggestions` builds bounded queries from persisted topics and sub-questions; `POST /api/research-runs/{run_id}/search-suggested` executes them and deduplicates candidate URLs.
- `POST /api/research-runs/{run_id}/sources/batch` saves up to ten reviewed candidates; `POST /api/research-runs/{run_id}/sources/collect-batch` collects all saved sources and reports per-source failures without hiding successful results.
- Source URLs are normalized per run to prevent duplicates, and finding insertion skips an existing identical statement for the same source.
- `GET /api/research-runs/{run_id}/details` aggregates the durable traceability chain for UI inspection without changing any records.
- Next milestone: add AI-assisted finding extraction with structured JSON validation.

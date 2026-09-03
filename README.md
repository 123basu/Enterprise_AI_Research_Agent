# Enterprise AI Research Agent

This repository is for building an Enterprise AI Research Agent step by step.

The goal is to let a user ask a research question, collect and store evidence from reliable sources, extract findings, compare evidence, detect contradictions, and generate a traceable conclusion.

## Product Goal

Build a research workflow that is:

- traceable
- modular
- testable at every step
- easy to extend
- safe for deterministic operations and AI-assisted reasoning

## Target Workflow

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

## Proposed Architecture

- Web frontend: user input, progress, results, evidence view
- Backend/API layer: validation, orchestration, workflow control
- AI intelligence layer: question analysis, extraction, comparison, classification, conclusion generation
- Data and knowledge layer: database for questions, sources, findings, metadata, citations, relationships
- External research layer: approved APIs and web sources for gathering information

## Build Principle

We will build this in small increments and verify each increment by running the app, checking the UI, reviewing the flow, and inspecting the codebase.

Deterministic logic should stay in normal software code.
AI should be used only where interpretation or reasoning adds value.

## Current Status

- [x] Project vision captured
- [x] Research pipeline defined
- [x] Layered architecture drafted
- [x] Project flow documentation started
- [x] AI context documentation started
- [x] Initial app skeleton
- [x] Frontend question entry UI
- [x] FastAPI backend scaffold
- [x] Research request API with placeholder pipeline stages
- [x] SQLite schema for research questions and research runs
- [x] Persist each submitted question and return its run ID
- [x] Sources table and manual source capture linked to research runs
- [x] Bounded source content collection with retrieval metadata
- [x] Baseline sentence-level finding extraction linked to sources
- [x] Citations with evidence text and character offsets
- [x] Cross-source evidence comparison with baseline contradiction signals
- [x] Deterministic finding classification with confidence scores
- [x] Traceable deterministic conclusion generation with uncertainty
- [x] Configurable Ollama/OpenRouter AI provider layer
- [x] AI structured finding extraction with evidence validation
- [x] AI comparison response validation and contradiction explanations
- [x] AI question analysis with persisted research topics
- [x] Source search adapter with ranked result selection
- [x] Derived workflow status across all completed stages
- [x] Automatic multi-query search from topics and sub-questions
- [x] Batch save and collection for reviewed source candidates
- [x] Source URL and finding deduplication
- [x] Run details and traceability inspection view
- [ ] Research workflow orchestration
- [ ] Storage layer and schema
- [x] Source collection integration
- [ ] Finding extraction pipeline
- [ ] AI-assisted finding extraction
- [x] AI-assisted finding extraction
- [ ] Evidence comparison and contradiction detection
- [ ] AI-assisted evidence comparison
- [x] AI-assisted evidence comparison
- [x] Deterministic conclusion generation
- [x] AI provider connection for conclusions
- [ ] AI conclusion evaluation and quality checks
- [ ] Traceability and audit views

## Suggested Step-by-Step Plan

### Step 1: Project skeleton and request flow

- [x] Create the base folder structure
- [x] Add the frontend and backend entry points
- [x] Add dependency setup
- [x] Add a health check and landing screen
- [x] Accept and validate a research question
- [x] Send the request to the backend
- [x] Return a stubbed workflow response

### Step 2: Data model

- [x] Define initial tables for research questions and research runs
- [x] Add schema initialization on application startup
- [x] Add a simple research-run listing endpoint
- [ ] Add sources, findings, citations, classifications, and traceability links

### Step 4: Source collection

- Add source search integration
- Store source metadata and collected content
- Keep every source tied to the originating question

### Step 5: AI extraction

- Extract findings from collected content
- Store extracted statements with citations
- Keep prompts and intermediate work temporary unless needed for audit

### Step 6: Evidence analysis

- Compare findings across sources
- Classify findings by type and confidence
- Detect contradictions and conflicts

### Step 7: Conclusions and traceability

- Generate a conclusion from the evidence
- Present the supporting chain from question to source to finding to conclusion
- Add an audit-friendly result view

### Step 8: Hardening

- Add tests
- Add logging
- Add error handling
- Improve performance and UX

## How We Will Work

At each step, we should be able to:

- run the app
- inspect the UI
- verify the API flow
- inspect the code structure
- confirm what is implemented and what is still missing

## Notes

- Keep the architecture simple unless a new component clearly adds value.
- Prefer PostgreSQL first.
- Add pgvector only if semantic retrieval becomes necessary.
- Use AI only for tasks that need interpretation, extraction, comparison, or reasoning.

## Run The Current Step

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000` and submit a question, add a source URL, then click `Collect`. Verify `http://127.0.0.1:8000/api/health`, `http://127.0.0.1:8000/api/research-runs`, and `/api/research-runs/{run_id}/sources`. Collection currently accepts text/HTML/JSON responses, limits content to 100,000 characters, and stores retrieval metadata in `data/research.db`.

After collection, click `Extract findings`. The current baseline extracts up to ten sentence-level observations from collected text and stores a citation for each finding with evidence character offsets. It is intentionally deterministic and is not a substitute for the future AI extraction layer.

After collecting a source, click `AI extract`. The model must return JSON findings containing exact `evidence_text`; unmatched evidence is discarded and the result is rejected if no evidence can be mapped back to the stored source content.

After starting a research run, click `Analyze question with AI`. The model returns structured research areas and focused sub-questions; research areas are persisted in `research_topics`.

Use the Search approved sources panel to search Wikipedia's public API. Results are candidates only; use `Use source`, review the URL, and save it through the existing source form before collecting content.

The Workflow state panel derives completion from durable records and can be refreshed after each action. It is the first orchestration view for the full research run.

After question analysis, `Search analyzed topics` builds up to eight queries from persisted topics and sub-questions, searches each query, removes duplicate URLs, and presents the candidates for review.

Use `Save all candidates` to save up to ten reviewed results to the current run, then `Collect saved sources` to retrieve them as a batch.

Sources are deduplicated per research run by normalized URL, and repeating extraction for the same source skips identical finding statements.

Use `Inspect run details` after starting a run to review the stored question, source previews, findings, evidence offsets, classifications, comparisons, and conclusion in one place.

After extracting findings from at least two sources, click `AI compare`. The model must return valid finding IDs and one of `supports`, `contradicts`, `unrelated`, or `uncertain`; invalid or same-source pairs are discarded.

After extracting findings from at least two sources, click `Compare evidence`. The baseline compares findings from different sources and marks opposite keyword signals as `potential_contradiction` for review.

Click `Classify findings` to assign each finding a visible baseline label such as `positive_signal`, `negative_signal`, or `neutral_observation`, with a confidence score.

Click `Generate conclusion` to save a run-level evidence summary linked to all extracted finding IDs. The conclusion reports the source/finding counts and explicitly warns when the baseline detector found potential contradictions.

Copy `.env.example` to `.env`, set `AI_PROVIDER` to `ollama` or `openrouter`, and set `AI_MODEL` to the model name. After classifying findings, click `Generate AI conclusion`. Ollama uses `OLLAMA_BASE_URL` and accepts either the server root (for example `http://localhost:11434/`) or the full `/api/chat` URL. OpenRouter requires `OPENROUTER_API_KEY` and uses `OPENROUTER_BASE_URL`.

If port `8000` is busy, choose another port explicitly:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8001
```

import json
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, HttpUrl, ValidationError

from app.ai import ai_config, ask_ai
from app.database import add_findings, add_source, classify_findings, create_research_run, get_collected_source, get_latest_conclusion, get_research_question, get_source, initialize_database, list_comparisons, list_findings, list_research_runs, list_sources, list_sub_questions, list_topics, save_comparisons, save_conclusion, save_source_content, save_topics
from app.search import build_search_queries, search_sources


BASE_DIR = Path(__file__).parent
app = FastAPI(title="Enterprise AI Research Agent", version="0.1.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
initialize_database()


class ResearchRequest(BaseModel):
    question: str = Field(min_length=10, max_length=500)


class SourceRequest(BaseModel):
    url: HttpUrl
    title: str = Field(min_length=1, max_length=300)
    source_type: str = Field(min_length=1, max_length=50)
    notes: str | None = Field(default=None, max_length=1000)


class AIFinding(BaseModel):
    statement: str = Field(min_length=1, max_length=1000)
    evidence_text: str = Field(min_length=1, max_length=1000)


class AIQuestionAnalysis(BaseModel):
    topics: list[str] = Field(min_length=1, max_length=8)
    sub_questions: list[str] = Field(min_length=1, max_length=10)


class SearchRequest(BaseModel):
    query: str = Field(min_length=3, max_length=200)


class SourceBatchRequest(BaseModel):
    sources: list[SourceRequest] = Field(min_length=1, max_length=10)


class AIComparison(BaseModel):
    finding_a_id: int
    finding_b_id: int
    relationship: Literal["supports", "contradicts", "unrelated", "uncertain"]
    rationale: str = Field(min_length=1, max_length=1000)


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip_tag: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.skip_tag = tag

    def handle_endtag(self, tag: str) -> None:
        if tag == self.skip_tag:
            self.skip_tag = None

    def handle_data(self, data: str) -> None:
        if self.skip_tag is None:
            self.parts.append(data)


def extract_sentences(content: str, content_type: str) -> list[tuple[str, int, int]]:
    if content_type == "text/html":
        parser = TextExtractor()
        parser.feed(content)
        content = " ".join(parser.parts)
    content = re.sub(r"\s+", " ", content).strip()
    matches = re.finditer(r"[^.!?]+[.!?]", content)
    return [(match.group().strip()[:1000], match.start(), match.end()) for match in matches if len(match.group().strip()) >= 40][:10]


def normalized_content(content: str, content_type: str) -> str:
    if content_type == "text/html":
        parser = TextExtractor()
        parser.feed(content)
        content = " ".join(parser.parts)
    return re.sub(r"\s+", " ", content).strip()


def extract_json_payload(text: str) -> str:
    cleaned = text.strip()
    if "```" in cleaned:
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1).strip()
    # Fallback: extract first JSON array/object
    if cleaned and cleaned[0] not in "[{":
        start_bracket = cleaned.find("[")
        start_brace = cleaned.find("{")
        starts = [s for s in [start_bracket, start_brace] if s != -1]
        if starts:
            start = min(starts)
            end_bracket = cleaned.rfind("]")
            end_brace = cleaned.rfind("}")
            end = max(end_bracket, end_brace)
            if end != -1 and end > start:
                cleaned = cleaned[start : end + 1].strip()
    return cleaned


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "research-agent"}


@app.get("/api/ai/config")
def ai_configuration() -> dict[str, str]:
    try:
        provider, model = ai_config()
    except ValueError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    return {"provider": provider, "model": model}


@app.get("/api/research-runs")
def research_runs() -> dict[str, object]:
    return {"runs": list_research_runs()}


@app.get("/api/research-runs/{run_id}/sources")
def sources(run_id: int) -> dict[str, object]:
    return {"run_id": run_id, "sources": list_sources(run_id)}


@app.get("/api/research-runs/{run_id}/topics")
def topics(run_id: int) -> dict[str, object]:
    return {"run_id": run_id, "topics": list_topics(run_id)}


@app.get("/api/research-runs/{run_id}/workflow")
def workflow_status(run_id: int) -> dict[str, object]:
    if get_research_question(run_id) is None:
        raise HTTPException(status_code=404, detail="Research run not found.")
    run_sources = list_sources(run_id)
    run_findings = list_findings(run_id)
    run_comparisons = list_comparisons(run_id)
    run_conclusion = get_latest_conclusion(run_id)
    stages = [
        {"name": "Research question", "status": "complete"},
        {"name": "Question analysis", "status": "complete" if list_topics(run_id) else "waiting"},
        {"name": "Source search", "status": "complete" if run_sources else "waiting"},
        {"name": "Source collection", "status": "complete" if run_sources and all(source["fetch_status"] == "collected" for source in run_sources) else "waiting"},
        {"name": "Finding extraction", "status": "complete" if run_findings else "waiting"},
        {"name": "Evidence comparison", "status": "complete" if run_comparisons else "waiting"},
        {"name": "Finding classification", "status": "complete" if run_findings and all(finding["classification"] != "unclassified" for finding in run_findings) else "waiting"},
        {"name": "Conclusion", "status": "complete" if run_conclusion else "waiting"},
        {"name": "Traceability", "status": "complete" if run_findings and all(finding["evidence_text"] for finding in run_findings) else "waiting"},
    ]
    complete = sum(stage["status"] == "complete" for stage in stages)
    return {"run_id": run_id, "complete_stages": complete, "total_stages": len(stages), "stages": stages}


@app.get("/api/research-runs/{run_id}/details")
def run_details(run_id: int) -> dict[str, object]:
    question = get_research_question(run_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Research run not found.")
    return {
        "run_id": run_id,
        "question": question["question"],
        "topics": list_topics(run_id),
        "sub_questions": list_sub_questions(run_id),
        "sources": list_sources(run_id),
        "findings": list_findings(run_id),
        "comparisons": list_comparisons(run_id),
        "conclusion": get_latest_conclusion(run_id),
    }


@app.post("/api/research-runs/{run_id}/search")
def search(run_id: int, request: SearchRequest) -> dict[str, object]:
    if get_research_question(run_id) is None:
        raise HTTPException(status_code=404, detail="Research run not found.")
    try:
        results = search_sources(request.query)
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return {"run_id": run_id, "query": request.query, "provider": "wikipedia", "results": results}


@app.get("/api/research-runs/{run_id}/search-suggestions")
def search_suggestions(run_id: int) -> dict[str, object]:
    question = get_research_question(run_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Research run not found.")
    queries = build_search_queries(question["question"], [topic["topic"] for topic in list_topics(run_id)], list_sub_questions(run_id))
    return {"run_id": run_id, "queries": queries}


@app.post("/api/research-runs/{run_id}/search-suggested")
def search_suggested(run_id: int) -> dict[str, object]:
    suggestions = search_suggestions(run_id)
    if not suggestions["queries"]:
        raise HTTPException(status_code=409, detail="Analyze the question before searching suggested topics.")
    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    failures: list[str] = []
    for query in suggestions["queries"]:
        try:
            for result in search_sources(query, limit=3):
                if result["url"] not in seen_urls:
                    result["query"] = query
                    results.append(result)
                    seen_urls.add(result["url"])
        except RuntimeError as error:
            failures.append(f"{query}: {error}")
            continue
    if not results and failures:
        raise HTTPException(status_code=502, detail="; ".join(failures))
    return {"run_id": run_id, "queries": suggestions["queries"], "provider": "wikipedia", "results": results}


@app.post("/api/research-runs/{run_id}/analyze-question")
def analyze_question(run_id: int) -> dict[str, object]:
    question = get_research_question(run_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Research run not found.")
    prompt = """Analyze this research question. Return ONLY a JSON object with two arrays: topics (1 to 8 concise research areas) and sub_questions (1 to 10 focused questions). Do not answer the questions and do not invent context.\n\nResearch question:\n""" + question["question"]
    try:
        response, provider, model = ask_ai(prompt)
        payload = extract_json_payload(response)
        analysis = AIQuestionAnalysis.model_validate(json.loads(payload))
    except (RuntimeError, ValueError, json.JSONDecodeError, TypeError, ValidationError) as error:
        raise HTTPException(status_code=502, detail=f"The AI returned an invalid question analysis: {error}") from error
    saved_topics = save_topics(question["id"], analysis.topics, analysis.sub_questions)
    return {"run_id": run_id, "provider": provider, "model": model, "topics": saved_topics, "sub_questions": analysis.sub_questions}


@app.post("/api/research-runs/{run_id}/sources", status_code=201)
def save_source(run_id: int, request: SourceRequest) -> dict[str, object]:
    return {"source": add_source(run_id, str(request.url), request.title, request.source_type, request.notes)}


@app.post("/api/research-runs/{run_id}/sources/batch", status_code=201)
def save_sources_batch(run_id: int, request: SourceBatchRequest) -> dict[str, object]:
    if get_research_question(run_id) is None:
        raise HTTPException(status_code=404, detail="Research run not found.")
    saved = [add_source(run_id, str(source.url), source.title, source.source_type, source.notes) for source in request.sources]
    return {"run_id": run_id, "sources": saved}


@app.post("/api/research-runs/{run_id}/sources/collect-batch")
def collect_sources_batch(run_id: int) -> dict[str, object]:
    if get_research_question(run_id) is None:
        raise HTTPException(status_code=404, detail="Research run not found.")
    results = []
    for source in list_sources(run_id):
        if source["fetch_status"] == "collected":
            results.append({"source_id": source["id"], "status": "already_collected"})
            continue
        try:
            results.append(collect_source(run_id, source["id"]))
        except HTTPException as error:
            results.append({"source_id": source["id"], "status": "failed", "detail": error.detail})
    return {"run_id": run_id, "results": results}


@app.post("/api/research-runs/{run_id}/sources/{source_id}/collect")
def collect_source(run_id: int, source_id: int) -> dict[str, object]:
    source = get_source(run_id, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found for this research run.")

    request = Request(source["url"], headers={"User-Agent": "EnterpriseResearchAgent/0.1"})
    try:
        with urlopen(request, timeout=10) as response:
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "text/plain", "application/json"}:
                raise HTTPException(status_code=415, detail=f"Unsupported content type: {content_type}")
            content = response.read(100_001).decode(response.headers.get_content_charset() or "utf-8", errors="replace")
    except HTTPError as error:
        raise HTTPException(status_code=502, detail=f"Source returned HTTP {error.code}.") from error
    except (URLError, TimeoutError) as error:
        raise HTTPException(status_code=502, detail="Source could not be reached.") from error

    truncated = len(content) > 100_000
    content = content[:100_000]
    save_source_content(source_id, content, content_type, "collected")
    return {"source_id": source_id, "status": "collected", "content_type": content_type, "characters": len(content), "truncated": truncated}


@app.get("/api/research-runs/{run_id}/findings")
def findings(run_id: int) -> dict[str, object]:
    return {"run_id": run_id, "findings": list_findings(run_id)}


@app.post("/api/research-runs/{run_id}/sources/{source_id}/extract")
def extract_source_findings(run_id: int, source_id: int) -> dict[str, object]:
    source = get_collected_source(run_id, source_id)
    if source is None:
        raise HTTPException(status_code=409, detail="Collect this source before extracting findings.")
    statements = extract_sentences(source["content"] or "", source["content_type"] or "text/plain")
    return {"run_id": run_id, "source_id": source_id, "findings": add_findings(run_id, source_id, statements)}


@app.post("/api/research-runs/{run_id}/sources/{source_id}/ai-extract")
def ai_extract_source_findings(run_id: int, source_id: int) -> dict[str, object]:
    source = get_collected_source(run_id, source_id)
    if source is None:
        raise HTTPException(status_code=409, detail="Collect this source before extracting findings.")
    content = normalized_content(source["content"] or "", source["content_type"] or "text/plain")
    prompt = """Extract up to 10 important findings from the source text. Return ONLY a JSON array. Each item must have exactly two string fields: statement and evidence_text. evidence_text must be copied exactly from the source text, not paraphrased. Do not invent facts.\n\nSource text:\n""" + content[:20_000]
    try:
        response, provider, model = ask_ai(prompt)
        payload = extract_json_payload(response)
        parsed = json.loads(payload)
        if isinstance(parsed, dict):
            parsed = parsed.get("findings")
        candidates = [AIFinding.model_validate(item) for item in parsed]
    except (RuntimeError, ValueError, json.JSONDecodeError, TypeError, ValidationError) as error:
        raise HTTPException(status_code=502, detail=f"The AI returned an invalid finding response: {error}") from error

    statements: list[tuple[str, int, int]] = []
    for candidate in candidates[:10]:
        start_char = content.find(candidate.evidence_text)
        if start_char >= 0:
            statements.append((candidate.statement, start_char, start_char + len(candidate.evidence_text)))
    if not statements:
        raise HTTPException(status_code=502, detail="The AI findings did not contain evidence matching the source text.")
    findings = add_findings(run_id, source_id, statements)
    return {"run_id": run_id, "source_id": source_id, "provider": provider, "model": model, "findings": findings}


def polarity(statement: str) -> str:
    positive = {"increase", "improve", "benefit", "support", "effective", "success"}
    negative = {"decrease", "harm", "risk", "worsen", "ineffective", "failure"}
    words = set(re.findall(r"[a-z]+", statement.lower()))
    has_positive = bool(words & positive)
    has_negative = bool(words & negative)
    if has_positive and not has_negative:
        return "positive"
    if has_negative and not has_positive:
        return "negative"
    return "neutral"


@app.get("/api/research-runs/{run_id}/comparisons")
def comparisons(run_id: int) -> dict[str, object]:
    return {"run_id": run_id, "comparisons": list_comparisons(run_id)}


@app.post("/api/research-runs/{run_id}/compare")
def compare_evidence(run_id: int) -> dict[str, object]:
    findings = list_findings(run_id)
    comparisons_to_save: list[tuple[int, int, str, str]] = []
    for index, finding_a in enumerate(findings):
        for finding_b in findings[index + 1 :]:
            if finding_a["source_id"] == finding_b["source_id"]:
                continue
            polarity_a = polarity(finding_a["statement"])
            polarity_b = polarity(finding_b["statement"])
            if {polarity_a, polarity_b} == {"positive", "negative"}:
                relationship = "potential_contradiction"
                rationale = "The baseline polarity signals point in opposite directions; human or AI review is required."
            else:
                relationship = "different_evidence"
                rationale = "The findings come from different sources and were retained for side-by-side review."
            comparisons_to_save.append((finding_a["id"], finding_b["id"], relationship, rationale))
    return {"run_id": run_id, "comparisons": save_comparisons(run_id, comparisons_to_save)}


@app.post("/api/research-runs/{run_id}/ai-compare")
def ai_compare_evidence(run_id: int) -> dict[str, object]:
    findings = list_findings(run_id)
    if len({finding["source_id"] for finding in findings}) < 2:
        raise HTTPException(status_code=409, detail="Add findings from at least two sources before comparing evidence.")
    evidence = "\n".join(f"Finding {finding['id']} (source {finding['source_id']}): {finding['statement']} | Evidence: {finding['evidence_text']}" for finding in findings)
    prompt = """Compare the findings below. Return ONLY a JSON array. Each item must contain finding_a_id, finding_b_id, relationship (one of supports, contradicts, unrelated, uncertain), and rationale. Compare only IDs that appear below. Do not invent facts. Return valid JSON with double quotes and commas.\n\n""" + evidence[:30_000]
    try:
        response, provider, model = ask_ai(prompt)
        payload = extract_json_payload(response)
        parsed = json.loads(payload)
        if isinstance(parsed, dict):
            parsed = parsed.get("comparisons")
        candidates = [AIComparison.model_validate(item) for item in parsed]
    except (RuntimeError, ValueError, json.JSONDecodeError, TypeError, ValidationError) as error:
        raise HTTPException(status_code=502, detail=f"The AI returned an invalid comparison response: {error}") from error

    valid_ids = {finding["id"] for finding in findings}
    valid_pairs = []
    source_by_id = {finding["id"]: finding["source_id"] for finding in findings}
    for candidate in candidates[:50]:
        if candidate.finding_a_id not in valid_ids or candidate.finding_b_id not in valid_ids:
            continue
        if candidate.finding_a_id == candidate.finding_b_id or source_by_id[candidate.finding_a_id] == source_by_id[candidate.finding_b_id]:
            continue
        valid_pairs.append((candidate.finding_a_id, candidate.finding_b_id, candidate.relationship, candidate.rationale))
    if not valid_pairs:
        raise HTTPException(status_code=502, detail="The AI comparison response contained no valid cross-source pairs.")
    return {"run_id": run_id, "provider": provider, "model": model, "comparisons": save_comparisons(run_id, valid_pairs, "ai", provider, model)}


@app.post("/api/research-runs/{run_id}/classify")
def classify_evidence(run_id: int) -> dict[str, object]:
    classifications: dict[int, tuple[str, float]] = {}
    for finding in list_findings(run_id):
        signal = polarity(finding["statement"])
        if signal == "positive":
            classification = ("positive_signal", 0.7)
        elif signal == "negative":
            classification = ("negative_signal", 0.7)
        else:
            classification = ("neutral_observation", 0.5)
        classifications[finding["id"]] = classification
    return {"run_id": run_id, "findings": classify_findings(run_id, classifications)}


@app.get("/api/research-runs/{run_id}/conclusion")
def conclusion(run_id: int) -> dict[str, object]:
    return {"run_id": run_id, "conclusion": get_latest_conclusion(run_id)}


@app.post("/api/research-runs/{run_id}/conclude")
def generate_conclusion(run_id: int) -> dict[str, object]:
    findings = list_findings(run_id)
    if not findings:
        raise HTTPException(status_code=409, detail="Extract findings before generating a conclusion.")
    if any(finding["classification"] == "unclassified" for finding in findings):
        raise HTTPException(status_code=409, detail="Classify findings before generating a conclusion.")
    sources = {finding["source_id"] for finding in findings}
    comparisons = list_comparisons(run_id)
    contradictions = [item for item in comparisons if item["relationship"] == "potential_contradiction"]
    positive = sum(finding["classification"] == "positive_signal" for finding in findings)
    negative = sum(finding["classification"] == "negative_signal" for finding in findings)
    summary = f"This research run contains {len(findings)} finding(s) from {len(sources)} source(s), including {positive} positive signal(s) and {negative} negative signal(s)."
    uncertainty = (
        f"{len(contradictions)} potential contradiction(s) were detected by the baseline heuristic; treat this conclusion as provisional and review the cited evidence."
        if contradictions
        else "No potential contradictions were detected by the baseline heuristic; review the cited evidence before relying on this conclusion."
    )
    return {"conclusion": save_conclusion(run_id, summary, uncertainty, [finding["id"] for finding in findings])}


@app.post("/api/research-runs/{run_id}/ai-conclude")
def generate_ai_conclusion(run_id: int) -> dict[str, object]:
    findings = list_findings(run_id)
    if not findings:
        raise HTTPException(status_code=409, detail="Extract findings before generating an AI conclusion.")
    if any(finding["classification"] == "unclassified" for finding in findings):
        raise HTTPException(status_code=409, detail="Classify findings before generating an AI conclusion.")
    prompt = """You are an enterprise research analyst. Write a concise conclusion using only the evidence below. State the main conclusion, mention disagreement or uncertainty, and do not invent facts. Do not include citations in your prose; the application already links each finding to its source.\n\nEvidence:\n""" + "\n".join(f"- Finding {finding['id']}: {finding['statement']} (source {finding['source_id']})" for finding in findings)
    try:
        summary, provider, model = ask_ai(prompt)
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    uncertainty = "AI-generated conclusion. Review the linked evidence and potential contradictions before relying on it."
    return {"conclusion": save_conclusion(run_id, summary, uncertainty, [finding["id"] for finding in findings], "ai", provider, model)}


@app.post("/api/research")
def research(request: ResearchRequest) -> dict[str, object]:
    question_id, run_id, created_at = create_research_run(request.question)
    stages = [
        "Research question received",
        "Search sources (placeholder)",
        "Collect information (placeholder)",
        "Store sources (placeholder)",
        "Extract findings (placeholder)",
        "Compare evidence (placeholder)",
        "Classify findings (placeholder)",
        "Detect contradictions (placeholder)",
        "Generate conclusions (placeholder)",
        "Maintain traceability (placeholder)",
    ]
    return {
        "question": request.question,
        "question_id": question_id,
        "run_id": run_id,
        "created_at": created_at,
        "status": "scaffold-ready",
        "message": "The workflow shell is connected. Research intelligence comes next.",
        "stages": stages,
        "findings": [],
        "sources": [],
    }

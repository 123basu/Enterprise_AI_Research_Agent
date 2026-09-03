import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen


def search_sources(query: str, limit: int = 5) -> list[dict[str, str]]:
    endpoint = "https://en.wikipedia.org/w/api.php?action=opensearch&namespace=0&format=json&limit=" + str(limit) + "&search=" + quote_plus(query)
    request = Request(endpoint, headers={"User-Agent": "EnterpriseResearchAgent/0.1"})
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read(200_000).decode())
    except HTTPError as error:
        raise RuntimeError(f"Search provider returned HTTP {error.code}.") from error
    except (URLError, TimeoutError) as error:
        raise RuntimeError("Search provider could not be reached.") from error
    return [{"title": title, "url": url, "snippet": snippet} for title, url, snippet in zip(payload[1], payload[3], payload[2])]


def build_search_queries(question: str, topics: list[str], sub_questions: list[str]) -> list[str]:
    candidates = [c.strip() for c in (topics + sub_questions) if c and c.strip()]
    deduped = list(dict.fromkeys(candidates))
    if deduped:
        return deduped[:8]
    # Fallback to question alone if no topics yet
    return [question.strip()][:1] if question and question.strip() else []

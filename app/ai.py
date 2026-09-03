import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def load_env() -> None:
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"\''))


load_env()


def ai_config() -> tuple[str, str]:
    provider = os.getenv("AI_PROVIDER", "ollama").lower()
    model = os.getenv("AI_MODEL", "llama3.2:3b")
    if provider not in {"ollama", "openrouter"}:
        raise ValueError("AI_PROVIDER must be 'ollama' or 'openrouter'.")
    return provider, model


def ask_ai(prompt: str) -> tuple[str, str, str]:
    provider, model = ai_config()
    if provider == "ollama":
        endpoint = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/api/chat").rstrip("/")
        if not endpoint.endswith("/api/chat"):
            endpoint += "/api/chat"
        headers = {"Content-Type": "application/json"}
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False}
    else:
        endpoint = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/chat/completions")
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is required when AI_PROVIDER=openrouter.")
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2}

    request = Request(endpoint, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urlopen(request, timeout=60) as response:
            result = json.loads(response.read(2_000_000).decode())
    except HTTPError as error:
        raise RuntimeError(f"{provider} returned HTTP {error.code}.") from error
    except (URLError, TimeoutError) as error:
        raise RuntimeError(f"Could not connect to {provider}.") from error

    content = result.get("message", {}).get("content") if provider == "ollama" else result.get("choices", [{}])[0].get("message", {}).get("content")
    if not content:
        raise RuntimeError(f"{provider} returned no message content.")
    return content.strip(), provider, model

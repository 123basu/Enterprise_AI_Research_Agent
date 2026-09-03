import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


DATA_DIR = Path(__file__).parent.parent / "data"
DATABASE_PATH = DATA_DIR / "research.db"


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database() -> None:
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS research_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS research_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY (question_id) REFERENCES research_questions (id)
            );

            CREATE TABLE IF NOT EXISTS research_topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER NOT NULL,
                topic TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (question_id) REFERENCES research_questions (id)
            );

            CREATE TABLE IF NOT EXISTS research_sub_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER NOT NULL,
                sub_question TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (question_id) REFERENCES research_questions (id)
            );

            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                title TEXT NOT NULL,
                source_type TEXT NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL,
                content TEXT,
                content_type TEXT,
                fetched_at TEXT,
                fetch_status TEXT NOT NULL DEFAULT 'not_collected',
                FOREIGN KEY (run_id) REFERENCES research_runs (id)
            );

            CREATE TABLE IF NOT EXISTS findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                source_id INTEGER NOT NULL,
                statement TEXT NOT NULL,
                finding_type TEXT NOT NULL,
                confidence REAL NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES research_runs (id),
                FOREIGN KEY (source_id) REFERENCES sources (id)
            );

            CREATE TABLE IF NOT EXISTS citations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                finding_id INTEGER NOT NULL,
                source_id INTEGER NOT NULL,
                evidence_text TEXT NOT NULL,
                start_char INTEGER NOT NULL,
                end_char INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (finding_id) REFERENCES findings (id),
                FOREIGN KEY (source_id) REFERENCES sources (id)
            );

            CREATE TABLE IF NOT EXISTS comparisons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                finding_a_id INTEGER NOT NULL,
                finding_b_id INTEGER NOT NULL,
                relationship TEXT NOT NULL,
                rationale TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES research_runs (id),
                FOREIGN KEY (finding_a_id) REFERENCES findings (id),
                FOREIGN KEY (finding_b_id) REFERENCES findings (id)
            );

            CREATE TABLE IF NOT EXISTS conclusions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                summary TEXT NOT NULL,
                uncertainty TEXT NOT NULL,
                created_at TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'deterministic',
                provider TEXT NOT NULL DEFAULT 'rules',
                model TEXT NOT NULL DEFAULT 'baseline',
                FOREIGN KEY (run_id) REFERENCES research_runs (id)
            );

            CREATE TABLE IF NOT EXISTS conclusion_findings (
                conclusion_id INTEGER NOT NULL,
                finding_id INTEGER NOT NULL,
                PRIMARY KEY (conclusion_id, finding_id),
                FOREIGN KEY (conclusion_id) REFERENCES conclusions (id),
                FOREIGN KEY (finding_id) REFERENCES findings (id)
            );
            """
        )
        columns = {row[1] for row in connection.execute("PRAGMA table_info(sources)")}
        for name, definition in {
            "content": "TEXT",
            "content_type": "TEXT",
            "fetched_at": "TEXT",
            "fetch_status": "TEXT NOT NULL DEFAULT 'not_collected'",
        }.items():
            if name not in columns:
                connection.execute(f"ALTER TABLE sources ADD COLUMN {name} {definition}")
        finding_columns = {row[1] for row in connection.execute("PRAGMA table_info(findings)")}
        if "classification" not in finding_columns:
            connection.execute("ALTER TABLE findings ADD COLUMN classification TEXT NOT NULL DEFAULT 'unclassified'")
        source_columns = {row[1] for row in connection.execute("PRAGMA table_info(sources)")}
        if "canonical_url" not in source_columns:
            connection.execute("ALTER TABLE sources ADD COLUMN canonical_url TEXT")
        for source_id, url in connection.execute("SELECT id, url FROM sources"):
            connection.execute("UPDATE sources SET canonical_url = ? WHERE id = ?", (normalize_url(url), source_id))
        conclusion_columns = {row[1] for row in connection.execute("PRAGMA table_info(conclusions)")}
        for name, definition in {"kind": "TEXT NOT NULL DEFAULT 'deterministic'", "provider": "TEXT NOT NULL DEFAULT 'rules'", "model": "TEXT NOT NULL DEFAULT 'baseline'"}.items():
            if name not in conclusion_columns:
                connection.execute(f"ALTER TABLE conclusions ADD COLUMN {name} {definition}")
        comparison_columns = {row[1] for row in connection.execute("PRAGMA table_info(comparisons)")}
        for name, definition in {"kind": "TEXT NOT NULL DEFAULT 'deterministic'", "provider": "TEXT NOT NULL DEFAULT 'rules'", "model": "TEXT NOT NULL DEFAULT 'baseline'"}.items():
            if name not in comparison_columns:
                connection.execute(f"ALTER TABLE comparisons ADD COLUMN {name} {definition}")


def create_research_run(question: str) -> tuple[int, int, str]:
    timestamp = datetime.now(timezone.utc).isoformat()
    with get_connection() as connection:
        question_cursor = connection.execute(
            "INSERT INTO research_questions (question, created_at) VALUES (?, ?)",
            (question, timestamp),
        )
        question_id = question_cursor.lastrowid
        run_cursor = connection.execute(
            "INSERT INTO research_runs (question_id, status, created_at) VALUES (?, ?, ?)",
            (question_id, "received", timestamp),
        )
        return question_id, run_cursor.lastrowid, timestamp


def get_research_question(run_id: int) -> dict[str, object] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT questions.id, questions.question FROM research_questions AS questions JOIN research_runs AS runs ON runs.question_id = questions.id WHERE runs.id = ?",
            (run_id,),
        ).fetchone()
    return dict(row) if row else None


def save_topics(question_id: int, topics: list[str], sub_questions: list[str] | None = None) -> list[dict[str, object]]:
    timestamp = datetime.now(timezone.utc).isoformat()
    with get_connection() as connection:
        connection.execute("DELETE FROM research_topics WHERE question_id = ?", (question_id,))
        connection.execute("DELETE FROM research_sub_questions WHERE question_id = ?", (question_id,))
        connection.executemany(
            "INSERT INTO research_topics (question_id, topic, created_at) VALUES (?, ?, ?)",
            [(question_id, topic, timestamp) for topic in topics],
        )
        connection.executemany(
            "INSERT INTO research_sub_questions (question_id, sub_question, created_at) VALUES (?, ?, ?)",
            [(question_id, sub_question, timestamp) for sub_question in (sub_questions or [])],
        )
        rows = connection.execute(
            "SELECT id, question_id, topic, created_at FROM research_topics WHERE question_id = ? ORDER BY id",
            (question_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_topics(run_id: int) -> list[dict[str, object]]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT topics.id, topics.question_id, topics.topic, topics.created_at FROM research_topics AS topics JOIN research_runs AS runs ON runs.question_id = topics.question_id WHERE runs.id = ? ORDER BY topics.id",
            (run_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_sub_questions(run_id: int) -> list[str]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT sub_questions.sub_question FROM research_sub_questions AS sub_questions JOIN research_runs AS runs ON runs.question_id = sub_questions.question_id WHERE runs.id = ? ORDER BY sub_questions.id",
            (run_id,),
        ).fetchall()
    return [row[0] for row in rows]


def list_research_runs() -> list[dict[str, object]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT runs.id, questions.question, runs.status, runs.created_at
            FROM research_runs AS runs
            JOIN research_questions AS questions ON questions.id = runs.question_id
            ORDER BY runs.id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def add_source(run_id: int, url: str, title: str, source_type: str, notes: str | None) -> dict[str, object]:
    timestamp = datetime.now(timezone.utc).isoformat()
    canonical_url = normalize_url(url)
    with get_connection() as connection:
        existing = connection.execute(
            "SELECT id, run_id, url, title, source_type, notes, created_at FROM sources WHERE run_id = ? AND canonical_url = ?",
            (run_id, canonical_url),
        ).fetchone()
        if existing:
            result = dict(existing)
            result["duplicate"] = True
            return result
        cursor = connection.execute(
            """
            INSERT INTO sources (run_id, url, canonical_url, title, source_type, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, url, canonical_url, title, source_type, notes, timestamp),
        )
        return {
            "id": cursor.lastrowid,
            "run_id": run_id,
            "url": url,
            "canonical_url": canonical_url,
            "title": title,
            "source_type": source_type,
            "notes": notes,
            "created_at": timestamp,
        }


def list_sources(run_id: int) -> list[dict[str, object]]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT id, run_id, url, title, source_type, notes, created_at, content_type, fetched_at, fetch_status, length(content) AS content_length, substr(content, 1, 600) AS content_preview FROM sources WHERE run_id = ? ORDER BY id",
            (run_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_source(run_id: int, source_id: int) -> dict[str, object] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT id, url FROM sources WHERE id = ? AND run_id = ?",
            (source_id, run_id),
        ).fetchone()
    return dict(row) if row else None


def save_source_content(source_id: int, content: str, content_type: str, status: str) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    with get_connection() as connection:
        connection.execute(
            "UPDATE sources SET content = ?, content_type = ?, fetched_at = ?, fetch_status = ? WHERE id = ?",
            (content, content_type, timestamp, status, source_id),
        )


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def get_collected_source(run_id: int, source_id: int) -> dict[str, object] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT id, content, content_type FROM sources WHERE id = ? AND run_id = ? AND fetch_status = 'collected'",
            (source_id, run_id),
        ).fetchone()
    return dict(row) if row else None


def add_findings(run_id: int, source_id: int, statements: list[tuple[str, int, int]]) -> list[dict[str, object]]:
    timestamp = datetime.now(timezone.utc).isoformat()
    with get_connection() as connection:
        for statement, start_char, end_char in statements:
            existing = connection.execute(
                "SELECT id FROM findings WHERE run_id = ? AND source_id = ? AND statement = ?",
                (run_id, source_id, statement),
            ).fetchone()
            if existing:
                continue
            finding_cursor = connection.execute(
                "INSERT INTO findings (run_id, source_id, statement, finding_type, confidence, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, source_id, statement, "observation", 0.5, timestamp),
            )
            connection.execute(
                "INSERT INTO citations (finding_id, source_id, evidence_text, start_char, end_char, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (finding_cursor.lastrowid, source_id, statement, start_char, end_char, timestamp),
            )
        rows = connection.execute(
            """
            SELECT findings.id, findings.run_id, findings.source_id, findings.statement,
                   findings.finding_type, findings.classification, findings.confidence, findings.created_at,
                   citations.evidence_text, citations.start_char, citations.end_char
            FROM findings
            JOIN citations ON citations.finding_id = findings.id
            WHERE findings.run_id = ? ORDER BY findings.id
            """,
            (run_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_findings(run_id: int) -> list[dict[str, object]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT findings.id, findings.run_id, findings.source_id, findings.statement,
                   findings.finding_type, findings.classification, findings.confidence, findings.created_at,
                   citations.evidence_text, citations.start_char, citations.end_char
            FROM findings
            JOIN citations ON citations.finding_id = findings.id
            WHERE findings.run_id = ? ORDER BY findings.id
            """,
            (run_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def classify_findings(run_id: int, classifications: dict[int, tuple[str, float]]) -> list[dict[str, object]]:
    with get_connection() as connection:
        for finding_id, (classification, confidence) in classifications.items():
            connection.execute(
                "UPDATE findings SET classification = ?, confidence = ? WHERE id = ? AND run_id = ?",
                (classification, confidence, finding_id, run_id),
            )
    return list_findings(run_id)


def save_comparisons(run_id: int, comparisons: list[tuple[int, int, str, str]], kind: str = "deterministic", provider: str = "rules", model: str = "baseline") -> list[dict[str, object]]:
    timestamp = datetime.now(timezone.utc).isoformat()
    with get_connection() as connection:
        connection.execute("DELETE FROM comparisons WHERE run_id = ?", (run_id,))
        for finding_a_id, finding_b_id, relationship, rationale in comparisons:
            connection.execute(
                "INSERT INTO comparisons (run_id, finding_a_id, finding_b_id, relationship, rationale, created_at, kind, provider, model) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, finding_a_id, finding_b_id, relationship, rationale, timestamp, kind, provider, model),
            )
        rows = connection.execute(
            "SELECT id, run_id, finding_a_id, finding_b_id, relationship, rationale, created_at, kind, provider, model FROM comparisons WHERE run_id = ? ORDER BY id",
            (run_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_comparisons(run_id: int) -> list[dict[str, object]]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT id, run_id, finding_a_id, finding_b_id, relationship, rationale, created_at, kind, provider, model FROM comparisons WHERE run_id = ? ORDER BY id",
            (run_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def save_conclusion(run_id: int, summary: str, uncertainty: str, finding_ids: list[int], kind: str = "deterministic", provider: str = "rules", model: str = "baseline") -> dict[str, object]:
    timestamp = datetime.now(timezone.utc).isoformat()
    with get_connection() as connection:
        conclusion = connection.execute(
            "INSERT INTO conclusions (run_id, summary, uncertainty, created_at, kind, provider, model) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (run_id, summary, uncertainty, timestamp, kind, provider, model),
        )
        conclusion_id = conclusion.lastrowid
        connection.executemany(
            "INSERT INTO conclusion_findings (conclusion_id, finding_id) VALUES (?, ?)",
            [(conclusion_id, finding_id) for finding_id in finding_ids],
        )
    return {"id": conclusion_id, "run_id": run_id, "summary": summary, "uncertainty": uncertainty, "finding_ids": finding_ids, "created_at": timestamp, "kind": kind, "provider": provider, "model": model}


def get_latest_conclusion(run_id: int) -> dict[str, object] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT id, run_id, summary, uncertainty, created_at, kind, provider, model FROM conclusions WHERE run_id = ? ORDER BY id DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        finding_rows = connection.execute(
            "SELECT finding_id FROM conclusion_findings WHERE conclusion_id = ? ORDER BY finding_id",
            (row["id"],),
        ).fetchall()
    result = dict(row)
    result["finding_ids"] = [finding[0] for finding in finding_rows]
    return result

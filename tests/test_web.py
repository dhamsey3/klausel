import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from klausel.rag import RetrievedContext
from klausel.vectorstore import SearchHit
from klausel.web import app as web

H = {"X-Klausel": "1"}


@pytest.fixture
def client():
    return TestClient(web.app, base_url="http://127.0.0.1")


def test_index_is_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "<title>Klausel</title>" in r.text


def test_api_requires_custom_header(client):
    assert client.get("/api/jobs/x").status_code == 403


def test_non_local_host_is_rejected():
    c = TestClient(web.app, base_url="http://evil.example")
    assert c.get("/", headers=H).status_code == 403


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Vertrag.PDF", "Vertrag.pdf"),
        ("../../etc/passwd.txt", "passwd.txt"),
        (r"C:\Users\x\Mietvertrag 2026.docx", "Mietvertrag 2026.docx"),
        ("a<b>|c?.md", "a_b_c_.md"),
    ],
)
def test_upload_names_are_sanitised(raw, expected):
    assert web._safe_name(raw) == expected


def test_upload_rejects_unsupported_type(client):
    r = client.post("/api/upload", headers=H, files={"file": ("x.exe", b"MZ")})
    assert r.status_code == 400


def test_ask_streams_sources_then_tokens(client, monkeypatch):
    hit = SearchHit(score=0.9, text="§ 3 Kündigung", source="s.txt", chunk_index=1, payload={})

    def fake_answer(question, *, top_k, source, lang):
        assert lang == "en"
        return RetrievedContext(hits=[hit]), iter(["Three ", "months [1]."])

    monkeypatch.setattr(web, "answer", fake_answer)
    r = client.post("/api/ask", headers=H, json={"question": "What notice period applies?"})
    events = [json.loads(line) for line in r.text.splitlines()]
    assert [e["type"] for e in events] == ["sources", "token", "token", "done"]
    assert events[0]["sources"][0] == {
        "n": 1,
        "source": "s.txt",
        "chunk": 1,
        "score": 0.9,
        "text": "§ 3 Kündigung",
    }
    assert "".join(e["text"] for e in events if e["type"] == "token") == "Three months [1]."

import pytest

from klausel.lang import detect_language
from klausel.rag import RetrievedContext, build_messages
from klausel.vectorstore import SearchHit


@pytest.mark.parametrize(
    "text,lang",
    [
        ("Welche Kündigungsfristen gelten in dem Vertrag?", "de"),
        ("Ist die Haftungsklausel wirksam?", "de"),
        ("What notice periods apply to the contract?", "en"),
        ("Is the liability clause valid?", "en"),
        ("Can the provider change prices without notice?", "en"),
        ("§ 4 Haftung", "de"),
    ],
)
def test_detects_question_language(text, lang):
    assert detect_language(text) == lang


def test_undecidable_text_uses_default():
    assert detect_language("DSGVO GDPR 2026", default="en") == "en"
    assert detect_language("", default="de") == "de"


def _ctx():
    hit = SearchHit(score=0.9, text="§ 4 Haftung ...", source="s.txt", chunk_index=3, payload={})
    return RetrievedContext(hits=[hit])


def test_english_question_gets_english_prompt_and_labels():
    system, user = build_messages("Is the liability clause valid?", _ctx(), "en")
    assert "Answer in English" in system["content"]
    assert user["content"].startswith("CONTEXT:\n[1] Source: s.txt (section 3)")
    assert "QUESTION:\nIs the liability clause valid?" in user["content"]


def test_german_question_gets_german_prompt_and_labels():
    system, user = build_messages("Ist die Haftungsklausel wirksam?", _ctx(), "de")
    assert "Antworte auf Deutsch" in system["content"]
    assert user["content"].startswith("KONTEXT:\n[1] Quelle: s.txt (Abschnitt 3)")

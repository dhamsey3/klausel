from klausel.ingest.redact import redact


def test_redacts_structured_identifiers():
    text = (
        "Kontakt: max.mustermann@example.com, Tel. +49 89 1234567, "
        "IBAN DE89 3704 0044 0532 0130 00, geb. am 01.02.1980."
    )
    r = redact(text)
    assert "example.com" not in r.text
    assert "1234567" not in r.text
    assert "DE89" not in r.text
    assert "1980" not in r.text
    assert r.counts["EMAIL"] == 1
    assert r.counts["IBAN"] == 1
    assert r.counts["PHONE"] == 1
    assert r.counts["BIRTHDATE"] == 1


def test_leaves_legal_references_alone():
    text = "Gemäß § 307 Abs. 1 BGB und Art. 28 DSGVO; Frist von 14 Tagen; 4.500,00 EUR; am 1. Januar 2026."
    r = redact(text)
    assert r.text == text
    assert not r.counts

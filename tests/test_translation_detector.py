from ai.translation_detector import TranslationDetector


def test_convert_keyword_detects_machine():
    cfg = {"AI_ALLOWED": False, "API_KEYS": {}}
    td = TranslationDetector(cfg)
    res = td.detect("Amazing Story (Convert).epub")
    assert res["translation_label"] == "machine_convert"
    assert res["method"] == "heuristic"
    assert res["confidence"] >= 0.8


def test_conflict_returns_unknown():
    cfg = {"AI_ALLOWED": False, "API_KEYS": {}}
    td = TranslationDetector(cfg)
    res = td.detect("Story (Convert - Dịch).epub")
    assert res["translation_label"] == "unknown"
    assert res["confidence"] == 0.0


def test_no_keywords_soft_proposal():
    cfg = {"AI_ALLOWED": False, "API_KEYS": {}}
    td = TranslationDetector(cfg)
    res = td.detect("Neutral Title.epub")
    assert res["translation_label"] == "unknown"
    assert res["method"] == "heuristic"
    assert 0.0 <= res["confidence"] <= 0.3

"""Unit tests for targeted file detection in context assembler."""

from app.services.context_assembler import _detect_file_targets


def _inventory(*filenames):
    return [{"filename": name} for name in filenames]


def test_detect_full_filename_match():
    inventory = _inventory("Master_Services_Agreement_Long_Form.pdf", "NDA_Template.docx")
    query = "In Master_Services_Agreement_Long_Form.pdf, what are the renewal terms?"

    matches, scores = _detect_file_targets(query, inventory)

    assert matches[0] == "Master_Services_Agreement_Long_Form.pdf"
    assert matches[0] in scores
    assert scores[matches[0]] > 0


def test_detect_alias_with_spaces_and_quotes():
    inventory = _inventory("Master_Services_Agreement_Long_Form.pdf", "NDA_Template.docx")
    query = 'Can you summarize the renewal clause in "Master Services Agreement"?'

    matches, _ = _detect_file_targets(query, inventory)

    assert matches[0] == "Master_Services_Agreement_Long_Form.pdf"


def test_missing_file_returns_empty():
    inventory = _inventory("NDA_Template.docx")
    query = "What does the MSA say about termination?"

    matches, scores = _detect_file_targets(query, inventory)

    assert matches == []
    assert scores == {}


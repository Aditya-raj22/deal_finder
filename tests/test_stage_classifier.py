"""Tests for stage classifier."""

import pytest

from deal_finder.classification.stage_classifier import StageClassifier
from deal_finder.models import DevelopmentStage


@pytest.fixture
def classifier():
    allowed_stages = ["preclinical", "phase 1", "phase I", "first-in-human", "FIH"]
    return StageClassifier(allowed_stages)


def test_classify_preclinical(classifier):
    text = "The preclinical candidate shows promise in early studies."
    stage, needs_review, evidence = classifier.classify(text)

    assert stage == DevelopmentStage.PRECLINICAL
    assert needs_review is False
    assert evidence is not None
    assert "preclinical" in evidence.raw_phrase.lower()


def test_classify_phase_1(classifier):
    text = "Phase 1 trial is expected to begin next quarter."
    stage, needs_review, evidence = classifier.classify(text)

    assert stage == DevelopmentStage.PHASE_1
    assert needs_review is False
    assert evidence is not None


def test_classify_first_in_human(classifier):
    text = "First-in-human study completed successfully."
    stage, needs_review, evidence = classifier.classify(text)

    assert stage == DevelopmentStage.FIRST_IN_HUMAN
    assert needs_review is False


def test_exclude_phase_2(classifier):
    text = "The company's phase 2 trial is ongoing."
    stage, needs_review, evidence = classifier.classify(text)

    assert stage is None
    assert needs_review is False  # Explicitly excluded


def test_ambiguous_phase_1_2(classifier):
    text = "Phase 1/2 study shows positive results."
    stage, needs_review, evidence = classifier.classify(text)

    assert stage == DevelopmentStage.PRECLINICAL  # Default for ambiguous
    assert needs_review is True  # Ambiguous


def test_no_stage_found(classifier):
    text = "No stage information in this text."
    stage, needs_review, evidence = classifier.classify(text)

    assert stage == DevelopmentStage.PRECLINICAL  # Default for unknown
    assert needs_review is True

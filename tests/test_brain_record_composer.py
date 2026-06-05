"""Tests for brain_record_composer."""

from __future__ import annotations

from autolinkingbrain.brain_record_composer import compose_entity_fact, infer_code_role


def test_infer_rest_controller():
    assert infer_code_role("api/PaymentController.kt", "@RestController class Payment") == "REST"


def test_compose_enriched():
    fact = compose_entity_fact(path="svc/UserService.kt", summary="User CRUD service", code_role="SERVICE")
    text = fact.enriched()
    assert "[ARCHITECTURE]" in text
    assert "[ROLE:SERVICE]" in text

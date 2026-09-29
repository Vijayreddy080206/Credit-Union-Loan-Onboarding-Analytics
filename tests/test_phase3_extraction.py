"""
Phase 3 Tests — LLM Extraction Service
"""
import pytest
from models.application import DocumentType
from schemas.extraction import FieldResult
from services.extraction.llm_adapter import MockLLMAdapter, _r

@pytest.mark.asyncio
async def test_mock_adapter_clean_id():
    adapter = MockLLMAdapter()
    text = "GOVERNMENT ISSUED ID\nFull Name: John Doe\nDate of Birth: 1990-01-01\nID Number: ID-123\nAddress: 123 Main St\nExpiry Date: 2030-01-01"
    result = await adapter.extract_government_id(text)
    
    assert result.full_name.value == "John Doe"
    assert result.full_name.confidence == 0.95
    assert not result.is_damaged
    assert result.min_confidence == 0.95

@pytest.mark.asyncio
async def test_mock_adapter_damaged_id():
    adapter = MockLLMAdapter()
    text = "DAMAGED\nGOVERNMENT ISSUED ID\nFull Name: John Doe\nDate of Birth: 1990-01-01\nID Number: ID-123\nAddress: 123 Main St\nExpiry Date: 2030-01-01"
    result = await adapter.extract_government_id(text)
    
    assert result.full_name.value == "John Doe"
    assert result.full_name.confidence == 0.55
    assert result.is_damaged
    assert result.min_confidence == 0.55

def test_field_result_is_confident():
    f1 = FieldResult(value="abc", confidence=0.9)
    assert f1.is_confident(0.8)
    
    f2 = FieldResult(value="abc", confidence=0.7)
    assert not f2.is_confident(0.8)
    
    f3 = FieldResult(value=None, confidence=0.9)
    assert not f3.is_confident(0.8)

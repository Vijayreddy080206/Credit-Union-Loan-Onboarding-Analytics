import pytest
from unittest.mock import patch, MagicMock
from uuid import uuid4
import httpx
from services.crm import crm_service

@pytest.mark.asyncio
async def test_crm_sync_success():
    app_id = uuid4()
    with patch("httpx.AsyncClient.post") as mock_post:
        # Mock successful responses for both contacts and deals
        mock_post.side_effect = [
            MagicMock(status_code=200, json=lambda: {"id": "contact_123"}, raise_for_status=lambda: None),
            MagicMock(status_code=200, json=lambda: {"id": "deal_123"}, raise_for_status=lambda: None)
        ]
        
        result = await crm_service.sync_application(app_id, "Test Name", "test@example.com", "SUBMITTED")
        
        assert result is True
        assert mock_post.call_count == 2

@pytest.mark.asyncio
async def test_crm_sync_retry_then_success():
    app_id = uuid4()
    with patch("httpx.AsyncClient.post") as mock_post:
        # Mock 1 failure, then success for contact, then success for deal
        mock_response_error = MagicMock()
        mock_response_error.raise_for_status.side_effect = httpx.HTTPStatusError("500 Error", request=MagicMock(), response=MagicMock())
        
        mock_post.side_effect = [
            httpx.HTTPStatusError("500 Error", request=MagicMock(), response=MagicMock()), # 1st try (fails)
            MagicMock(status_code=200, json=lambda: {"id": "contact_123"}, raise_for_status=lambda: None), # 2nd try (contact success)
            MagicMock(status_code=200, json=lambda: {"id": "deal_123"}, raise_for_status=lambda: None) # deal success
        ]
        
        result = await crm_service.sync_application(app_id, "Test Name", "test@example.com", "SUBMITTED")
        
        assert result is True
        assert mock_post.call_count == 3

@pytest.mark.asyncio
async def test_crm_sync_failure_after_retries():
    app_id = uuid4()
    with patch("httpx.AsyncClient.post") as mock_post:
        # Mock repeated failures
        mock_post.side_effect = httpx.HTTPStatusError("500 Error", request=MagicMock(), response=MagicMock())
        
        result = await crm_service.sync_application(app_id, "Test Name", "test@example.com", "SUBMITTED")
        
        assert result is False
        assert mock_post.call_count == 5 # stopped after 5 attempts

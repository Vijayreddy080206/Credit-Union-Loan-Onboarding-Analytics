import pytest
from httpx import AsyncClient, ASGITransport
import uuid
from unittest.mock import AsyncMock, patch
from api.main import app
from models.application import ApplicationStatus, Application

@pytest.fixture
def mock_db():
    with patch("api.routers.applications.get_db") as m_db:
        session_mock = AsyncMock()
        m_db.return_value = [session_mock]
        yield session_mock

@pytest.mark.asyncio
async def test_api_idempotency_creates_one_record():
    # We will patch the DB session to simulate existing record
    idemp_key = f"idemp_{uuid.uuid4()}"
    payload = {
        "idempotency_key": idemp_key,
        "applicant_name": "Idempotent User",
        "applicant_email": "idem@example.com",
        "requested_loan_amount": 10000.0,
        "loan_purpose": "Test"
    }
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with patch("api.routers.applications.get_db") as m_db:
            session_mock = AsyncMock()
            
            # First request: return None for existing app
            # meaning it doesn't exist
            class MockResult1:
                def scalar_one_or_none(self):
                    return None
            session_mock.execute.return_value = MockResult1()
            
            from datetime import datetime, timezone
            async def mock_refresh(obj, *args, **kwargs):
                if isinstance(obj, Application) and obj.id is None:
                    obj.id = uuid.uuid4()
                    obj.created_at = datetime.now(timezone.utc)
                    obj.updated_at = datetime.now(timezone.utc)
            session_mock.refresh.side_effect = mock_refresh
            
            # Also mock the ID assignment that happens during flush
            async def mock_flush(*args, **kwargs):
                pass
            session_mock.flush = mock_flush
            
            # Wait, easier to override dependency in app
            from core.database import get_db
            
            async def override_get_db():
                yield session_mock
                
            app.dependency_overrides[get_db] = override_get_db
            
            resp1 = await client.post("/applications/", json=payload)
            assert resp1.status_code == 200
            
            from datetime import datetime, timezone
            existing_app = Application(
                id=uuid.UUID(resp1.json()["id"]),
                idempotency_key=idemp_key,
                applicant_name="Idempotent User",
                applicant_email="idem@example.com",
                requested_loan_amount=10000.0,
                status=ApplicationStatus.SUBMITTED,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            class MockResult2:
                def scalar_one_or_none(self):
                    return existing_app
                    
            session_mock.execute.return_value = MockResult2()
            
            resp2 = await client.post("/applications/", json=payload)
            assert resp2.status_code == 200
            
            assert resp1.json()["id"] == resp2.json()["id"]
            app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_crm_sync_failure_stops_process():
    app_id = uuid.uuid4()
    transport = ASGITransport(app=app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        from core.database import get_db
        session_mock = AsyncMock()
        
        # Mock application lookup
        from datetime import datetime, timezone
        mock_app = Application(
            id=app_id,
            applicant_name="Test User",
            applicant_email="test@example.com",
            requested_loan_amount=1000.0,
            status=ApplicationStatus.SUBMITTED,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        
        class MockResultApp:
            def scalar_one_or_none(self): return mock_app
        class MockResultDocs:
            def scalars(self):
                class ScalarsMock:
                    def all(self): return []
                return ScalarsMock()
        
        session_mock.execute.side_effect = [MockResultApp(), MockResultDocs()]
        
        async def override_get_db():
            yield session_mock
            
        app.dependency_overrides[get_db] = override_get_db
        
        with patch("services.crm.CRMService.sync_application") as mock_sync:
            mock_sync.side_effect = Exception("CRM Sync Failed")
            
            with patch("services.rules_engine.rules_engine.evaluate") as mock_eval:
                mock_eval.return_value.decision = ApplicationStatus.AUTO_APPROVED
                mock_eval.return_value.rejection_reason = None
                mock_eval.return_value.flags = []
                mock_eval.return_value.model_dump.return_value = {}
                
                resp = await client.post(f"/applications/{app_id}/process")
                
                assert resp.status_code == 500
                assert "CRM Sync Failed" in resp.json()["detail"]
                session_mock.rollback.assert_called_once()
        
        app.dependency_overrides.clear()

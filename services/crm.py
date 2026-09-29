"""
Mock CRM Integration Service.

In a real environment, this would call Salesforce, Hubspot, etc.
Here, we just simulate creating a contact and deal.
"""
import httpx
import structlog
from uuid import UUID
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type

logger = structlog.get_logger(__name__)

CRM_BASE_URL = "http://mock-crm:8080"  # Configured in docker-compose

class CRMService:
    
    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential_jitter(initial=1, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
        before_sleep=lambda retry_state: logger.warning(
            "crm_sync_retry", 
            attempt=retry_state.attempt_number, 
            error=str(retry_state.outcome.exception())
        )
    )
    async def _do_sync(self, app_id: UUID, applicant_name: str, applicant_email: str, status: str):
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 1. Create or update contact
            contact_resp = await client.post(
                f"{CRM_BASE_URL}/contacts",
                json={"name": applicant_name, "email": applicant_email}
            )
            contact_resp.raise_for_status()
            contact_id = contact_resp.json().get("id")

            # 2. Update Deal status
            deal_resp = await client.post(
                f"{CRM_BASE_URL}/deals",
                json={
                    "application_id": str(app_id),
                    "contact_id": contact_id,
                    "status": status
                }
            )
            deal_resp.raise_for_status()
            return True

    async def sync_application(self, app_id: UUID, applicant_name: str, applicant_email: str, status: str):
        """Syncs the application state to the CRM."""
        logger.info("syncing_to_crm", app_id=str(app_id), status=status)
        try:
            await self._do_sync(app_id, applicant_name, applicant_email, status)
            logger.info("crm_sync_successful", app_id=str(app_id))
            return True
        except Exception as e:
            logger.error("crm_sync_failed", app_id=str(app_id), error=str(e))
            # We don't want to fail the whole application process if CRM is down
            return False

crm_service = CRMService()

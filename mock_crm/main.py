"""
Mock CRM service — mirrors the HubSpot/Zoho REST API shape.

Design note: building a mock with the same REST contract as the real CRM means:
1. Your integration code works in dev/CI without real credentials.
2. You can run contract tests against this mock.
3. Swapping to real HubSpot/Zoho only requires changing CRM_PROVIDER= in .env
   — the integration service code is untouched.

This is the "anti-corruption layer" / "adapter pattern" in practice.
"""

import uuid
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Mock CRM", description="Synthetic CRM for dev/test. Not a real CRM.")

# In-memory store (fine for dev; use Postgres in staging)
contacts: dict[str, dict] = {}
deals: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Schemas (match HubSpot's shape closely enough to be swappable)
# ---------------------------------------------------------------------------

class ContactUpsertRequest(BaseModel):
    idempotency_key: str
    properties: dict[str, Any]


class DealUpsertRequest(BaseModel):
    idempotency_key: str
    contact_id: str
    properties: dict[str, Any]


class ContactResponse(BaseModel):
    id: str
    properties: dict[str, Any]
    created_at: str
    updated_at: str


class DealResponse(BaseModel):
    id: str
    contact_id: str
    properties: dict[str, Any]
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "service": "mock-crm"}


@app.post("/crm/v3/objects/contacts", response_model=ContactResponse)
def upsert_contact(req: ContactUpsertRequest):
    """
    Idempotent upsert: if a contact with this idempotency_key already exists,
    update it and return the existing id. Otherwise create a new one.
    """
    existing = next(
        (c for c in contacts.values() if c["idempotency_key"] == req.idempotency_key),
        None,
    )
    now = datetime.utcnow().isoformat()
    if existing:
        existing["properties"].update(req.properties)
        existing["updated_at"] = now
        return ContactResponse(**existing)

    contact_id = str(uuid.uuid4())
    record = {
        "id": contact_id,
        "idempotency_key": req.idempotency_key,
        "properties": req.properties,
        "created_at": now,
        "updated_at": now,
    }
    contacts[contact_id] = record
    return ContactResponse(**record)


@app.get("/crm/v3/objects/contacts/{contact_id}", response_model=ContactResponse)
def get_contact(contact_id: str):
    if contact_id not in contacts:
        raise HTTPException(status_code=404, detail="Contact not found")
    return ContactResponse(**contacts[contact_id])


@app.post("/crm/v3/objects/deals", response_model=DealResponse)
def upsert_deal(req: DealUpsertRequest):
    """Idempotent deal upsert — same pattern as contacts."""
    existing = next(
        (d for d in deals.values() if d["idempotency_key"] == req.idempotency_key),
        None,
    )
    now = datetime.utcnow().isoformat()
    if existing:
        existing["properties"].update(req.properties)
        existing["updated_at"] = now
        return DealResponse(**existing)

    deal_id = str(uuid.uuid4())
    record = {
        "id": deal_id,
        "idempotency_key": req.idempotency_key,
        "contact_id": req.contact_id,
        "properties": req.properties,
        "created_at": now,
        "updated_at": now,
    }
    deals[deal_id] = record
    return DealResponse(**record)


@app.get("/crm/v3/objects/deals/{deal_id}", response_model=DealResponse)
def get_deal(deal_id: str):
    if deal_id not in deals:
        raise HTTPException(status_code=404, detail="Deal not found")
    return DealResponse(**deals[deal_id])


@app.get("/crm/v3/objects/contacts")
def list_contacts():
    return {"results": list(contacts.values()), "total": len(contacts)}


@app.get("/crm/v3/objects/deals")
def list_deals():
    return {"results": list(deals.values()), "total": len(deals)}

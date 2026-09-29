"""
Pydantic schemas for the Rules Engine (Phase 4).
"""
from typing import Optional
from pydantic import BaseModel
from models.application import ApplicationStatus

class RuleResult(BaseModel):
    passed: bool
    flag: Optional[str] = None
    reason: Optional[str] = None

class RulesEngineResult(BaseModel):
    decision: ApplicationStatus
    flags: list[str] = []
    rejection_reason: Optional[str] = None

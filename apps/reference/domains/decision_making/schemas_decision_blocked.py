from pydantic import BaseModel, Field

class DecisionBlockedPayload(BaseModel):
    """
    Schema for EVT:DECISION_BLOCKED.
    Signals that decision making process was halted prematurely due to configuration
    or other health-related blockers, before an intent could be formed.
    """
    schema_version: int = Field(default=1)
    
    # Context
    symbol: str = Field(description="Symbol being processed when block occurred")
    stage: str = Field(description="Pipeline stage where block occurred (e.g. 'on_features')")
    ts_ms: int = Field(description="Timestamp of the block in ms")
    
    # Reason
    reason_code: str = Field(description="Normalized Reject Reason code (e.g. NRR-CFG-001)")
    reason: str = Field(description="Human readable reason")
    
    # Debug details
    path: str = Field(description="Config path or resource involved")
    why: str = Field(description="Short explanation (<80 chars)")

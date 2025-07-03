# File: schemas/enrichment_status.py

from enum import Enum
from typing import Literal

class EnrichmentStatus(str, Enum):
    """
    Simple enrichment status values for articles.
    Status is set programmatically based on the enrichment process result.
    """
    PENDING = "pending"    # Not yet attempted
    SUCCESS = "success"    # Successfully enriched with content
    FAILED = "failed"      # No content found (search failed or parse failed)
    ERROR = "error"        # Technical error during process

# Type alias for better type hints
EnrichmentStatusType = Literal["pending", "success", "failed", "error"]

def normalize_enrichment_status(status: str) -> EnrichmentStatus:
    """
    Normalize legacy status strings to the simple 4-value system.
    Only needed for cleaning up existing inconsistent data.
    """
    if not status:
        return EnrichmentStatus.PENDING
    
    status_lower = status.lower().strip()
    
    # Success variations
    if status_lower in ["success", "successful", "completed", "enriched", "done"]:
        return EnrichmentStatus.SUCCESS
    
    # Failed variations (no content found)
    if status_lower in ["failed", "search_failed", "parse_failed", "no_queries", "skipped"]:
        return EnrichmentStatus.FAILED
    
    # Error variations (technical problems)
    if status_lower in ["error", "timeout", "crash"]:
        return EnrichmentStatus.ERROR
    
    # Default to pending for unknown statuses
    return EnrichmentStatus.PENDING
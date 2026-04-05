"""
Cloud backup — encrypted checkpoint storage with per-user rate limiting.

Supports: AWS S3, GCS, Azure Blob (pluggable via storage backend).
Restrictions: each user's upload/download bandwidth is capped
based on their contribution tier.
"""
from .backup import CloudBackup, BackupRecord
from .rate_limiter import CloudRateLimiter

__all__ = ["CloudBackup", "BackupRecord", "CloudRateLimiter"]

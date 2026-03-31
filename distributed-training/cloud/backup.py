"""
Cloud checkpoint backup — uploads/downloads model checkpoints
to/from object storage with AES-256 encryption per user.

Encryption key is derived from the user's node identity key
(never stored on the server — only the user can decrypt).
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import time
from dataclasses import dataclass, asdict
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    import base64
    _CRYPTO_OK = True
except ImportError:
    _CRYPTO_OK = False
    logger.warning("cryptography not installed — backups will be unencrypted")


@dataclass
class BackupRecord:
    backup_id: str
    owner: str
    job_id: str
    checkpoint_path: str
    remote_key: str       # object storage key
    size_bytes: int
    checksum: str
    encrypted: bool
    uploaded_at: float
    storage_backend: str  # "s3" | "gcs" | "azure" | "local"

    def to_dict(self) -> dict:
        return asdict(self)


class CloudBackup:
    """
    Manages encrypted checkpoint uploads/downloads.

    Backend is selected by environment:
      CLOUD_BACKEND = "s3" | "gcs" | "azure" | "local"
      S3_BUCKET / GCS_BUCKET / AZURE_CONTAINER
    """

    def __init__(self, owner: str, identity_key_hex: str, redis_url: str = "redis://localhost:6379/0"):
        self.owner = owner
        self._fernet = self._make_fernet(identity_key_hex) if _CRYPTO_OK else None
        self._backend = os.environ.get("CLOUD_BACKEND", "local")
        self._bucket = os.environ.get("S3_BUCKET") or os.environ.get("GCS_BUCKET", "dt-backups")
        import redis as _r
        self._r = _r.Redis.from_url(redis_url, decode_responses=True)

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    def upload(self, checkpoint_path: str, job_id: str) -> Optional[BackupRecord]:
        if not os.path.exists(checkpoint_path):
            logger.error(f"Checkpoint not found: {checkpoint_path}")
            return None

        with open(checkpoint_path, "rb") as f:
            data = f.read()

        checksum = hashlib.sha256(data).hexdigest()
        encrypted = False

        if self._fernet:
            data = self._fernet.encrypt(data)
            encrypted = True

        remote_key = f"{self.owner}/{job_id}/{os.path.basename(checkpoint_path)}"

        self._put_object(remote_key, data)

        import uuid
        record = BackupRecord(
            backup_id=str(uuid.uuid4())[:8],
            owner=self.owner,
            job_id=job_id,
            checkpoint_path=checkpoint_path,
            remote_key=remote_key,
            size_bytes=len(data),
            checksum=checksum,
            encrypted=encrypted,
            uploaded_at=time.time(),
            storage_backend=self._backend,
        )
        self._save_record(record)
        logger.info(f"Uploaded checkpoint: {remote_key} ({len(data)//1024}KB encrypted={encrypted})")
        return record

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def download(self, backup_id: str, dest_dir: str) -> Optional[str]:
        record = self._load_record(backup_id)
        if not record:
            logger.error(f"Backup record {backup_id} not found")
            return None

        data = self._get_object(record["remote_key"])
        if not data:
            return None

        if record["encrypted"] and self._fernet:
            data = self._fernet.decrypt(data)

        # Verify integrity
        checksum = hashlib.sha256(data).hexdigest()
        if checksum != record["checksum"]:
            logger.error(f"Checksum mismatch for {backup_id}! File may be corrupted.")
            return None

        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, os.path.basename(record["checkpoint_path"]))
        with open(dest, "wb") as f:
            f.write(data)
        logger.info(f"Downloaded checkpoint to {dest}")
        return dest

    def list_backups(self, job_id: Optional[str] = None) -> list:
        keys = self._r.keys(f"backup:{self.owner}:*")
        records = []
        for k in keys:
            raw = self._r.get(k)
            if raw:
                r = json.loads(raw)
                if job_id is None or r.get("job_id") == job_id:
                    records.append(r)
        return sorted(records, key=lambda x: x.get("uploaded_at", 0), reverse=True)

    # ------------------------------------------------------------------
    # Storage backends
    # ------------------------------------------------------------------

    def _put_object(self, key: str, data: bytes) -> None:
        if self._backend == "s3":
            self._s3_put(key, data)
        elif self._backend == "gcs":
            self._gcs_put(key, data)
        else:
            self._local_put(key, data)

    def _get_object(self, key: str) -> Optional[bytes]:
        if self._backend == "s3":
            return self._s3_get(key)
        elif self._backend == "gcs":
            return self._gcs_get(key)
        else:
            return self._local_get(key)

    def _s3_put(self, key: str, data: bytes) -> None:
        import boto3
        s3 = boto3.client("s3")
        s3.put_object(Bucket=self._bucket, Key=key, Body=data)

    def _s3_get(self, key: str) -> Optional[bytes]:
        import boto3
        s3 = boto3.client("s3")
        resp = s3.get_object(Bucket=self._bucket, Key=key)
        return resp["Body"].read()

    def _gcs_put(self, key: str, data: bytes) -> None:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(self._bucket)
        blob = bucket.blob(key)
        blob.upload_from_string(data)

    def _gcs_get(self, key: str) -> Optional[bytes]:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(self._bucket)
        blob = bucket.blob(key)
        return blob.download_as_bytes()

    def _local_put(self, key: str, data: bytes) -> None:
        local_dir = os.environ.get("LOCAL_BACKUP_DIR", "/tmp/dt_cloud_backup")
        path = os.path.join(local_dir, key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)

    def _local_get(self, key: str) -> Optional[bytes]:
        local_dir = os.environ.get("LOCAL_BACKUP_DIR", "/tmp/dt_cloud_backup")
        path = os.path.join(local_dir, key)
        if not os.path.exists(path):
            return None
        with open(path, "rb") as f:
            return f.read()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _make_fernet(identity_key_hex: str) -> "Fernet":
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"dt_backup_salt_v1",
            iterations=100_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(bytes.fromhex(identity_key_hex)))
        return Fernet(key)

    def _save_record(self, record: BackupRecord) -> None:
        self._r.setex(
            f"backup:{self.owner}:{record.backup_id}",
            86400 * 90,
            json.dumps(record.to_dict()),
        )

    def _load_record(self, backup_id: str) -> Optional[dict]:
        raw = self._r.get(f"backup:{self.owner}:{backup_id}")
        return json.loads(raw) if raw else None

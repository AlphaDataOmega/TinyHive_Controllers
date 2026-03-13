"""
Storage Controller for TinyHive

A unified storage controller supporting multiple backends:
- Local filesystem
- S3-compatible (AWS S3, MinIO, Cloudflare R2, DigitalOcean Spaces)
- SFTP

Profile Configuration:
----------------------
Profiles are stored in profiles/{name}.json

Local filesystem profile:
{
    "backend": "local",
    "base_path": "/data/storage",
    "create_dirs": true
}

S3-compatible profile:
{
    "backend": "s3",
    "bucket": "my-bucket",
    "region": "us-east-1",
    "endpoint_url": null,  // For MinIO, R2, etc.
    "access_key_env": "AWS_ACCESS_KEY_ID",
    "secret_key_env": "AWS_SECRET_ACCESS_KEY",
    "presigned_expiry": 3600
}

SFTP profile:
{
    "backend": "sftp",
    "host": "sftp.example.com",
    "port": 22,
    "username": "user",
    "password_env": "SFTP_PASSWORD",  // Or use key_path
    "key_path": null,
    "base_path": "/upload"
}

Required Permissions:
--------------------
- Local: Read/write access to base_path
- S3: s3:GetObject, s3:PutObject, s3:DeleteObject, s3:ListBucket
- SFTP: Read/write access on remote server

Dependencies:
------------
- Local: None (standard library only)
- S3: None (implements SigV4 signing)
- SFTP: paramiko (optional, install with: pip install paramiko)
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import shutil
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("tinyhive.controller.storage")

PROFILES_DIR = Path(__file__).parent.parent / "profiles"


# =============================================================================
# Abstract Backend
# =============================================================================

class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    def list_files(self, path: str = "", recursive: bool = False) -> List[Dict[str, Any]]:
        """List files at the given path."""
        pass

    @abstractmethod
    def upload_file(self, local_path: str, remote_path: str) -> Dict[str, Any]:
        """Upload a file from local path to remote path."""
        pass

    @abstractmethod
    def upload_content(self, content: bytes, remote_path: str) -> Dict[str, Any]:
        """Upload content directly to remote path."""
        pass

    @abstractmethod
    def download_file(self, remote_path: str, local_path: str) -> Dict[str, Any]:
        """Download a file from remote path to local path."""
        pass

    @abstractmethod
    def download_content(self, remote_path: str) -> Dict[str, Any]:
        """Download file content directly."""
        pass

    @abstractmethod
    def delete_file(self, remote_path: str) -> Dict[str, Any]:
        """Delete a file at the given path."""
        pass

    @abstractmethod
    def get_file_info(self, remote_path: str) -> Dict[str, Any]:
        """Get metadata about a file."""
        pass

    @abstractmethod
    def copy_file(self, src_path: str, dst_path: str) -> Dict[str, Any]:
        """Copy a file from source to destination."""
        pass

    @abstractmethod
    def move_file(self, src_path: str, dst_path: str) -> Dict[str, Any]:
        """Move a file from source to destination."""
        pass

    def get_presigned_url(self, remote_path: str, expiry: int = 3600) -> Dict[str, Any]:
        """Get a presigned URL for the file (if supported)."""
        return {"ok": False, "error": "Presigned URLs not supported for this backend"}


# =============================================================================
# Local Filesystem Backend
# =============================================================================

class LocalBackend(StorageBackend):
    """Local filesystem storage backend."""

    def __init__(self, config: Dict[str, Any]):
        self.base_path = Path(config.get("base_path", "/tmp/storage"))
        self.create_dirs = config.get("create_dirs", True)
        if self.create_dirs:
            self.base_path.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, path: str) -> Path:
        """Resolve path relative to base, with traversal protection."""
        resolved = (self.base_path / path).resolve()
        if not str(resolved).startswith(str(self.base_path.resolve())):
            raise ValueError(f"Path traversal detected: {path}")
        return resolved

    def list_files(self, path: str = "", recursive: bool = False) -> List[Dict[str, Any]]:
        target = self._resolve_path(path)
        if not target.exists():
            return []

        files = []
        if recursive:
            for item in target.rglob("*"):
                if item.is_file():
                    stat = item.stat()
                    files.append({
                        "path": str(item.relative_to(self.base_path)),
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                        "is_dir": False
                    })
        else:
            for item in target.iterdir():
                stat = item.stat()
                files.append({
                    "path": str(item.relative_to(self.base_path)),
                    "size": stat.st_size if item.is_file() else 0,
                    "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                    "is_dir": item.is_dir()
                })
        return files

    def upload_file(self, local_path: str, remote_path: str) -> Dict[str, Any]:
        src = Path(local_path)
        if not src.exists():
            return {"ok": False, "error": f"Local file not found: {local_path}"}

        dst = self._resolve_path(remote_path)
        if self.create_dirs:
            dst.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy2(src, dst)
        return {"ok": True, "path": str(dst.relative_to(self.base_path)), "size": dst.stat().st_size}

    def upload_content(self, content: bytes, remote_path: str) -> Dict[str, Any]:
        dst = self._resolve_path(remote_path)
        if self.create_dirs:
            dst.parent.mkdir(parents=True, exist_ok=True)

        dst.write_bytes(content)
        return {"ok": True, "path": str(dst.relative_to(self.base_path)), "size": len(content)}

    def download_file(self, remote_path: str, local_path: str) -> Dict[str, Any]:
        src = self._resolve_path(remote_path)
        if not src.exists():
            return {"ok": False, "error": f"Remote file not found: {remote_path}"}

        dst = Path(local_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return {"ok": True, "local_path": str(dst), "size": dst.stat().st_size}

    def download_content(self, remote_path: str) -> Dict[str, Any]:
        src = self._resolve_path(remote_path)
        if not src.exists():
            return {"ok": False, "error": f"Remote file not found: {remote_path}"}

        content = src.read_bytes()
        # Return as text if possible, otherwise base64
        try:
            return {"ok": True, "content": content.decode("utf-8"), "encoding": "utf-8", "size": len(content)}
        except UnicodeDecodeError:
            return {"ok": True, "content": base64.b64encode(content).decode("ascii"), "encoding": "base64", "size": len(content)}

    def delete_file(self, remote_path: str) -> Dict[str, Any]:
        target = self._resolve_path(remote_path)
        if not target.exists():
            return {"ok": False, "error": f"File not found: {remote_path}"}

        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return {"ok": True, "deleted": remote_path}

    def get_file_info(self, remote_path: str) -> Dict[str, Any]:
        target = self._resolve_path(remote_path)
        if not target.exists():
            return {"ok": False, "error": f"File not found: {remote_path}"}

        stat = target.stat()
        return {
            "ok": True,
            "path": remote_path,
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "created": datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat(),
            "is_dir": target.is_dir()
        }

    def copy_file(self, src_path: str, dst_path: str) -> Dict[str, Any]:
        src = self._resolve_path(src_path)
        if not src.exists():
            return {"ok": False, "error": f"Source file not found: {src_path}"}

        dst = self._resolve_path(dst_path)
        if self.create_dirs:
            dst.parent.mkdir(parents=True, exist_ok=True)

        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        return {"ok": True, "src": src_path, "dst": dst_path}

    def move_file(self, src_path: str, dst_path: str) -> Dict[str, Any]:
        src = self._resolve_path(src_path)
        if not src.exists():
            return {"ok": False, "error": f"Source file not found: {src_path}"}

        dst = self._resolve_path(dst_path)
        if self.create_dirs:
            dst.parent.mkdir(parents=True, exist_ok=True)

        shutil.move(src, dst)
        return {"ok": True, "src": src_path, "dst": dst_path}


# =============================================================================
# S3-Compatible Backend
# =============================================================================

class S3Backend(StorageBackend):
    """S3-compatible storage backend using AWS Signature V4."""

    def __init__(self, config: Dict[str, Any]):
        self.bucket = config["bucket"]
        self.region = config.get("region", "us-east-1")
        self.endpoint_url = config.get("endpoint_url")
        self.presigned_expiry = config.get("presigned_expiry", 3600)

        access_key_env = config.get("access_key_env", "AWS_ACCESS_KEY_ID")
        secret_key_env = config.get("secret_key_env", "AWS_SECRET_ACCESS_KEY")

        self.access_key = os.environ.get(access_key_env)
        self.secret_key = os.environ.get(secret_key_env)

        if not self.access_key or not self.secret_key:
            raise ValueError(f"Missing credentials: {access_key_env} or {secret_key_env}")

        if self.endpoint_url:
            self.host = urllib.parse.urlparse(self.endpoint_url).netloc
        else:
            self.host = f"{self.bucket}.s3.{self.region}.amazonaws.com"

    def _sign_v4(self, method: str, path: str, headers: Dict[str, str],
                 payload: bytes = b"", query_params: Dict[str, str] = None) -> Dict[str, str]:
        """Generate AWS Signature V4 headers."""
        now = datetime.utcnow()
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")

        headers = dict(headers)
        headers["x-amz-date"] = amz_date
        headers["host"] = self.host

        # Payload hash
        payload_hash = hashlib.sha256(payload).hexdigest()
        headers["x-amz-content-sha256"] = payload_hash

        # Canonical request
        signed_headers = ";".join(sorted(k.lower() for k in headers.keys()))
        canonical_headers = "".join(f"{k.lower()}:{v}\n" for k, v in sorted(headers.items()))

        query_string = ""
        if query_params:
            query_string = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}"
                                   for k, v in sorted(query_params.items()))

        canonical_request = f"{method}\n{path}\n{query_string}\n{canonical_headers}\n{signed_headers}\n{payload_hash}"

        # String to sign
        algorithm = "AWS4-HMAC-SHA256"
        credential_scope = f"{date_stamp}/{self.region}/s3/aws4_request"
        string_to_sign = f"{algorithm}\n{amz_date}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode()).hexdigest()}"

        # Signing key
        def sign(key, msg):
            return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

        k_date = sign(f"AWS4{self.secret_key}".encode("utf-8"), date_stamp)
        k_region = sign(k_date, self.region)
        k_service = sign(k_region, "s3")
        k_signing = sign(k_service, "aws4_request")

        signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        headers["Authorization"] = (
            f"{algorithm} Credential={self.access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )

        return headers

    def _request(self, method: str, key: str, data: bytes = None,
                 query_params: Dict[str, str] = None) -> urllib.request.Request:
        """Build a signed S3 request."""
        path = f"/{key}" if not self.endpoint_url else f"/{self.bucket}/{key}"

        headers = {}
        if data:
            headers["Content-Length"] = str(len(data))
            headers["Content-Type"] = "application/octet-stream"

        signed_headers = self._sign_v4(method, path, headers, data or b"", query_params)

        if self.endpoint_url:
            url = f"{self.endpoint_url}/{self.bucket}/{key}"
        else:
            url = f"https://{self.host}/{key}"

        if query_params:
            url += "?" + "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}"
                                  for k, v in query_params.items())

        req = urllib.request.Request(url, data=data, headers=signed_headers, method=method)
        return req

    def _execute(self, req: urllib.request.Request) -> bytes:
        """Execute request and return response body."""
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            raise Exception(f"S3 error {e.code}: {e.read().decode('utf-8', errors='replace')}")

    def list_files(self, path: str = "", recursive: bool = False) -> List[Dict[str, Any]]:
        params = {"list-type": "2"}
        if path:
            params["prefix"] = path.lstrip("/")
        if not recursive:
            params["delimiter"] = "/"

        req = self._request("GET", "", query_params=params)
        response = self._execute(req)

        # Parse XML response (simple extraction)
        files = []
        import re
        for match in re.finditer(r"<Key>([^<]+)</Key>.*?<Size>(\d+)</Size>.*?<LastModified>([^<]+)</LastModified>",
                                 response.decode("utf-8"), re.DOTALL):
            files.append({
                "path": match.group(1),
                "size": int(match.group(2)),
                "modified": match.group(3),
                "is_dir": False
            })
        # Common prefixes (directories)
        for match in re.finditer(r"<CommonPrefixes><Prefix>([^<]+)</Prefix></CommonPrefixes>",
                                 response.decode("utf-8")):
            files.append({
                "path": match.group(1),
                "size": 0,
                "modified": None,
                "is_dir": True
            })
        return files

    def upload_file(self, local_path: str, remote_path: str) -> Dict[str, Any]:
        src = Path(local_path)
        if not src.exists():
            return {"ok": False, "error": f"Local file not found: {local_path}"}

        content = src.read_bytes()
        return self.upload_content(content, remote_path)

    def upload_content(self, content: bytes, remote_path: str) -> Dict[str, Any]:
        key = remote_path.lstrip("/")
        req = self._request("PUT", key, data=content)
        self._execute(req)
        return {"ok": True, "path": key, "size": len(content)}

    def download_file(self, remote_path: str, local_path: str) -> Dict[str, Any]:
        result = self.download_content(remote_path)
        if not result["ok"]:
            return result

        content = result["content"]
        if result["encoding"] == "base64":
            content = base64.b64decode(content)
        else:
            content = content.encode("utf-8")

        dst = Path(local_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(content)
        return {"ok": True, "local_path": str(dst), "size": len(content)}

    def download_content(self, remote_path: str) -> Dict[str, Any]:
        key = remote_path.lstrip("/")
        req = self._request("GET", key)
        try:
            content = self._execute(req)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        try:
            return {"ok": True, "content": content.decode("utf-8"), "encoding": "utf-8", "size": len(content)}
        except UnicodeDecodeError:
            return {"ok": True, "content": base64.b64encode(content).decode("ascii"), "encoding": "base64", "size": len(content)}

    def delete_file(self, remote_path: str) -> Dict[str, Any]:
        key = remote_path.lstrip("/")
        req = self._request("DELETE", key)
        try:
            self._execute(req)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "deleted": key}

    def get_file_info(self, remote_path: str) -> Dict[str, Any]:
        key = remote_path.lstrip("/")
        req = self._request("HEAD", key)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return {
                    "ok": True,
                    "path": key,
                    "size": int(resp.headers.get("Content-Length", 0)),
                    "modified": resp.headers.get("Last-Modified"),
                    "content_type": resp.headers.get("Content-Type"),
                    "etag": resp.headers.get("ETag", "").strip('"')
                }
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"ok": False, "error": f"File not found: {key}"}
            return {"ok": False, "error": f"S3 error {e.code}"}

    def copy_file(self, src_path: str, dst_path: str) -> Dict[str, Any]:
        src_key = src_path.lstrip("/")
        dst_key = dst_path.lstrip("/")

        # S3 copy requires x-amz-copy-source header
        path = f"/{dst_key}" if not self.endpoint_url else f"/{self.bucket}/{dst_key}"
        headers = {"x-amz-copy-source": f"/{self.bucket}/{src_key}"}
        signed = self._sign_v4("PUT", path, headers)

        if self.endpoint_url:
            url = f"{self.endpoint_url}/{self.bucket}/{dst_key}"
        else:
            url = f"https://{self.host}/{dst_key}"

        req = urllib.request.Request(url, headers=signed, method="PUT")
        try:
            self._execute(req)
        except Exception as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "src": src_key, "dst": dst_key}

    def move_file(self, src_path: str, dst_path: str) -> Dict[str, Any]:
        copy_result = self.copy_file(src_path, dst_path)
        if not copy_result["ok"]:
            return copy_result

        delete_result = self.delete_file(src_path)
        if not delete_result["ok"]:
            return {"ok": False, "error": f"Copy succeeded but delete failed: {delete_result['error']}"}

        return {"ok": True, "src": src_path.lstrip("/"), "dst": dst_path.lstrip("/")}

    def get_presigned_url(self, remote_path: str, expiry: int = None) -> Dict[str, Any]:
        """Generate a presigned URL for downloading."""
        key = remote_path.lstrip("/")
        expiry = expiry or self.presigned_expiry

        now = datetime.utcnow()
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")

        credential_scope = f"{date_stamp}/{self.region}/s3/aws4_request"

        params = {
            "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
            "X-Amz-Credential": f"{self.access_key}/{credential_scope}",
            "X-Amz-Date": amz_date,
            "X-Amz-Expires": str(expiry),
            "X-Amz-SignedHeaders": "host"
        }

        path = f"/{key}" if not self.endpoint_url else f"/{self.bucket}/{key}"
        query_string = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}"
                               for k, v in sorted(params.items()))

        canonical_request = f"GET\n{path}\n{query_string}\nhost:{self.host}\n\nhost\nUNSIGNED-PAYLOAD"

        string_to_sign = f"AWS4-HMAC-SHA256\n{amz_date}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode()).hexdigest()}"

        def sign(key, msg):
            return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

        k_date = sign(f"AWS4{self.secret_key}".encode("utf-8"), date_stamp)
        k_region = sign(k_date, self.region)
        k_service = sign(k_region, "s3")
        k_signing = sign(k_service, "aws4_request")

        signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        if self.endpoint_url:
            url = f"{self.endpoint_url}/{self.bucket}/{key}?{query_string}&X-Amz-Signature={signature}"
        else:
            url = f"https://{self.host}/{key}?{query_string}&X-Amz-Signature={signature}"

        return {"ok": True, "url": url, "expires_in": expiry}


# =============================================================================
# SFTP Backend
# =============================================================================

class SFTPBackend(StorageBackend):
    """SFTP storage backend using paramiko."""

    def __init__(self, config: Dict[str, Any]):
        try:
            import paramiko
            self.paramiko = paramiko
        except ImportError:
            raise ImportError("SFTP backend requires paramiko: pip install paramiko")

        self.host = config["host"]
        self.port = config.get("port", 22)
        self.username = config["username"]
        self.base_path = config.get("base_path", "/")

        # Auth: password or key
        password_env = config.get("password_env")
        self.password = os.environ.get(password_env) if password_env else None
        self.key_path = config.get("key_path")

        if not self.password and not self.key_path:
            raise ValueError("SFTP requires either password_env or key_path")

    def _connect(self):
        """Establish SFTP connection."""
        transport = self.paramiko.Transport((self.host, self.port))
        if self.key_path:
            key = self.paramiko.RSAKey.from_private_key_file(self.key_path)
            transport.connect(username=self.username, pkey=key)
        else:
            transport.connect(username=self.username, password=self.password)
        return self.paramiko.SFTPClient.from_transport(transport)

    def _resolve_path(self, path: str) -> str:
        """Resolve path relative to base."""
        if path.startswith("/"):
            return path
        return f"{self.base_path.rstrip('/')}/{path}"

    def list_files(self, path: str = "", recursive: bool = False) -> List[Dict[str, Any]]:
        sftp = self._connect()
        try:
            target = self._resolve_path(path)
            files = []

            def list_dir(dir_path):
                for attr in sftp.listdir_attr(dir_path):
                    full_path = f"{dir_path}/{attr.filename}"
                    rel_path = full_path[len(self.base_path):].lstrip("/")
                    is_dir = attr.st_mode and (attr.st_mode & 0o40000)
                    files.append({
                        "path": rel_path,
                        "size": attr.st_size or 0,
                        "modified": datetime.fromtimestamp(attr.st_mtime, tz=timezone.utc).isoformat() if attr.st_mtime else None,
                        "is_dir": bool(is_dir)
                    })
                    if recursive and is_dir:
                        list_dir(full_path)

            list_dir(target)
            return files
        finally:
            sftp.close()

    def upload_file(self, local_path: str, remote_path: str) -> Dict[str, Any]:
        src = Path(local_path)
        if not src.exists():
            return {"ok": False, "error": f"Local file not found: {local_path}"}

        sftp = self._connect()
        try:
            target = self._resolve_path(remote_path)
            sftp.put(str(src), target)
            return {"ok": True, "path": remote_path, "size": src.stat().st_size}
        finally:
            sftp.close()

    def upload_content(self, content: bytes, remote_path: str) -> Dict[str, Any]:
        sftp = self._connect()
        try:
            target = self._resolve_path(remote_path)
            with sftp.open(target, "wb") as f:
                f.write(content)
            return {"ok": True, "path": remote_path, "size": len(content)}
        finally:
            sftp.close()

    def download_file(self, remote_path: str, local_path: str) -> Dict[str, Any]:
        sftp = self._connect()
        try:
            target = self._resolve_path(remote_path)
            dst = Path(local_path)
            dst.parent.mkdir(parents=True, exist_ok=True)
            sftp.get(target, str(dst))
            return {"ok": True, "local_path": str(dst), "size": dst.stat().st_size}
        finally:
            sftp.close()

    def download_content(self, remote_path: str) -> Dict[str, Any]:
        sftp = self._connect()
        try:
            target = self._resolve_path(remote_path)
            with sftp.open(target, "rb") as f:
                content = f.read()
            try:
                return {"ok": True, "content": content.decode("utf-8"), "encoding": "utf-8", "size": len(content)}
            except UnicodeDecodeError:
                return {"ok": True, "content": base64.b64encode(content).decode("ascii"), "encoding": "base64", "size": len(content)}
        finally:
            sftp.close()

    def delete_file(self, remote_path: str) -> Dict[str, Any]:
        sftp = self._connect()
        try:
            target = self._resolve_path(remote_path)
            try:
                sftp.remove(target)
            except IOError:
                sftp.rmdir(target)
            return {"ok": True, "deleted": remote_path}
        finally:
            sftp.close()

    def get_file_info(self, remote_path: str) -> Dict[str, Any]:
        sftp = self._connect()
        try:
            target = self._resolve_path(remote_path)
            attr = sftp.stat(target)
            return {
                "ok": True,
                "path": remote_path,
                "size": attr.st_size or 0,
                "modified": datetime.fromtimestamp(attr.st_mtime, tz=timezone.utc).isoformat() if attr.st_mtime else None,
                "is_dir": bool(attr.st_mode and (attr.st_mode & 0o40000))
            }
        except IOError as e:
            return {"ok": False, "error": str(e)}
        finally:
            sftp.close()

    def copy_file(self, src_path: str, dst_path: str) -> Dict[str, Any]:
        # SFTP doesn't support server-side copy, so download and upload
        result = self.download_content(src_path)
        if not result["ok"]:
            return result

        content = result["content"]
        if result["encoding"] == "base64":
            content = base64.b64decode(content)
        else:
            content = content.encode("utf-8")

        return self.upload_content(content, dst_path)

    def move_file(self, src_path: str, dst_path: str) -> Dict[str, Any]:
        sftp = self._connect()
        try:
            src = self._resolve_path(src_path)
            dst = self._resolve_path(dst_path)
            sftp.rename(src, dst)
            return {"ok": True, "src": src_path, "dst": dst_path}
        except IOError as e:
            return {"ok": False, "error": str(e)}
        finally:
            sftp.close()


# =============================================================================
# Profile Management
# =============================================================================

def load_profile(name: str) -> Dict[str, Any]:
    """Load a named profile from the profiles directory."""
    profile_path = PROFILES_DIR / f"{name}.json"
    if not profile_path.exists():
        raise FileNotFoundError(f"Profile not found: {name}")

    with open(profile_path) as f:
        return json.load(f)


def get_backend(profile_name: str) -> StorageBackend:
    """Get a storage backend instance for the given profile."""
    config = load_profile(profile_name)
    backend_type = config.get("backend", "local")

    if backend_type == "local":
        return LocalBackend(config)
    elif backend_type == "s3":
        return S3Backend(config)
    elif backend_type == "sftp":
        return SFTPBackend(config)
    else:
        raise ValueError(f"Unknown backend type: {backend_type}")


# =============================================================================
# Actions
# =============================================================================

def list_files(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    List files at a path.

    Params:
        path (str): Path to list (default: root)
        recursive (bool): List recursively (default: false)
    """
    try:
        backend = get_backend(profile_name)
        files = backend.list_files(
            path=params.get("path", ""),
            recursive=params.get("recursive", False)
        )
        return {"ok": True, "files": files, "count": len(files)}
    except Exception as e:
        logger.exception("list_files failed")
        return {"ok": False, "error": str(e)}


def upload_file(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Upload a file.

    Params:
        local_path (str): Path to local file (required if content not provided)
        content (str): File content to upload (base64 for binary)
        content_encoding (str): 'utf-8' or 'base64' (default: utf-8)
        remote_path (str): Destination path (required)
    """
    try:
        backend = get_backend(profile_name)
        remote_path = params.get("remote_path")
        if not remote_path:
            return {"ok": False, "error": "remote_path is required"}

        if "content" in params:
            content = params["content"]
            encoding = params.get("content_encoding", "utf-8")
            if encoding == "base64":
                content = base64.b64decode(content)
            else:
                content = content.encode("utf-8")
            return backend.upload_content(content, remote_path)
        elif "local_path" in params:
            return backend.upload_file(params["local_path"], remote_path)
        else:
            return {"ok": False, "error": "Either local_path or content is required"}
    except Exception as e:
        logger.exception("upload_file failed")
        return {"ok": False, "error": str(e)}


def download_file(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Download a file.

    Params:
        remote_path (str): Path to remote file (required)
        local_path (str): Local destination (optional, returns content if not provided)
    """
    try:
        backend = get_backend(profile_name)
        remote_path = params.get("remote_path")
        if not remote_path:
            return {"ok": False, "error": "remote_path is required"}

        if "local_path" in params:
            return backend.download_file(remote_path, params["local_path"])
        else:
            return backend.download_content(remote_path)
    except Exception as e:
        logger.exception("download_file failed")
        return {"ok": False, "error": str(e)}


def delete_file(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete a file.

    Params:
        path (str): Path to delete (required)
    """
    try:
        backend = get_backend(profile_name)
        path = params.get("path")
        if not path:
            return {"ok": False, "error": "path is required"}
        return backend.delete_file(path)
    except Exception as e:
        logger.exception("delete_file failed")
        return {"ok": False, "error": str(e)}


def get_file_info(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get file metadata.

    Params:
        path (str): Path to file (required)
    """
    try:
        backend = get_backend(profile_name)
        path = params.get("path")
        if not path:
            return {"ok": False, "error": "path is required"}
        return backend.get_file_info(path)
    except Exception as e:
        logger.exception("get_file_info failed")
        return {"ok": False, "error": str(e)}


def copy_file(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Copy a file.

    Params:
        src (str): Source path (required)
        dst (str): Destination path (required)
    """
    try:
        backend = get_backend(profile_name)
        src = params.get("src")
        dst = params.get("dst")
        if not src or not dst:
            return {"ok": False, "error": "src and dst are required"}
        return backend.copy_file(src, dst)
    except Exception as e:
        logger.exception("copy_file failed")
        return {"ok": False, "error": str(e)}


def move_file(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Move a file.

    Params:
        src (str): Source path (required)
        dst (str): Destination path (required)
    """
    try:
        backend = get_backend(profile_name)
        src = params.get("src")
        dst = params.get("dst")
        if not src or not dst:
            return {"ok": False, "error": "src and dst are required"}
        return backend.move_file(src, dst)
    except Exception as e:
        logger.exception("move_file failed")
        return {"ok": False, "error": str(e)}


def get_presigned_url(profile_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a presigned URL for a file (S3 only).

    Params:
        path (str): Path to file (required)
        expiry (int): URL expiry in seconds (default: from profile or 3600)
    """
    try:
        backend = get_backend(profile_name)
        path = params.get("path")
        if not path:
            return {"ok": False, "error": "path is required"}
        return backend.get_presigned_url(path, params.get("expiry"))
    except Exception as e:
        logger.exception("get_presigned_url failed")
        return {"ok": False, "error": str(e)}


# =============================================================================
# Action Registry & Dispatch
# =============================================================================

ACTIONS = {
    "list_files": list_files,
    "upload_file": upload_file,
    "download_file": download_file,
    "delete_file": delete_file,
    "get_file_info": get_file_info,
    "copy_file": copy_file,
    "move_file": move_file,
    "get_presigned_url": get_presigned_url,
}


def execute(profile: str, action: str, params: Dict[str, Any]) -> Any:
    """
    Main dispatch entry point.

    Called by ControllerDispatch with:
        - profile: The profile name from method_id
        - action: The action name from method_id
        - params: Action parameters

    Returns action result dict.
    """
    if action not in ACTIONS:
        return {"ok": False, "error": f"Unknown action: {action}"}

    logger.info(f"Executing storage.{profile}.{action}")
    return ACTIONS[action](profile, params)

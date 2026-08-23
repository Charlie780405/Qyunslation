# SPDX-License-Identifier: MPL-2.0
from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from pathlib import Path


class StorageBackend(ABC):
    name: str

    @abstractmethod
    def put_bytes(self, key: str, data: bytes) -> None:
        ...

    @abstractmethod
    def put_file(self, key: str, src_path: Path) -> None:
        ...

    @abstractmethod
    def get_bytes(self, key: str) -> bytes:
        ...

    @abstractmethod
    def open_path(self, key: str) -> Path | None:
        """本地可读路径；对象存储返回 None。"""
        ...

    @abstractmethod
    def exists(self, key: str) -> bool:
        ...

    @abstractmethod
    def list_prefix(self, prefix: str) -> list[str]:
        ...


class LocalStorageBackend(StorageBackend):
    name = "local"

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = key.lstrip("/").replace("..", "_")
        return self.root / safe

    def put_bytes(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def put_file(self, key: str, src_path: Path) -> None:
        dest = self._path(key)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dest)

    def get_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def open_path(self, key: str) -> Path | None:
        path = self._path(key)
        return path if path.is_file() else None

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def list_prefix(self, prefix: str) -> list[str]:
        base = self._path(prefix)
        if not base.exists():
            return []
        if base.is_file():
            return [prefix]
        keys: list[str] = []
        for p in base.rglob("*"):
            if p.is_file():
                rel = p.relative_to(self.root).as_posix()
                keys.append(rel)
        return sorted(keys)


class MinioStorageBackend(StorageBackend):
    name = "minio"

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = False,
        prefix: str = "pdf2zh",
    ):
        try:
            from minio import Minio
        except ImportError as exc:
            raise RuntimeError(
                "MinIO 后端需要安装 minio：uv pip install minio"
            ) from exc

        endpoint = endpoint.replace("https://", "").replace("http://", "")
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        if not self.client.bucket_exists(bucket):
            self.client.make_bucket(bucket)

    def _object_name(self, key: str) -> str:
        key = key.lstrip("/")
        return f"{self.prefix}/{key}" if self.prefix else key

    def put_bytes(self, key: str, data: bytes) -> None:
        from io import BytesIO

        self.client.put_object(
            self.bucket,
            self._object_name(key),
            BytesIO(data),
            length=len(data),
        )

    def put_file(self, key: str, src_path: Path) -> None:
        self.client.fput_object(
            self.bucket, self._object_name(key), str(src_path)
        )

    def get_bytes(self, key: str) -> bytes:
        resp = self.client.get_object(self.bucket, self._object_name(key))
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    def open_path(self, key: str) -> Path | None:
        return None

    def exists(self, key: str) -> bool:
        try:
            self.client.stat_object(self.bucket, self._object_name(key))
            return True
        except Exception:
            return False

    def list_prefix(self, prefix: str) -> list[str]:
        full_prefix = self._object_name(prefix)
        keys: list[str] = []
        for obj in self.client.list_objects(
            self.bucket, prefix=full_prefix, recursive=True
        ):
            name = obj.object_name or ""
            if self.prefix and name.startswith(f"{self.prefix}/"):
                name = name[len(self.prefix) + 1 :]
            keys.append(name)
        return sorted(keys)


def build_storage_backend(
    backend: str,
    local_root: Path,
    *,
    minio_endpoint: str = "",
    minio_access_key: str = "",
    minio_secret_key: str = "",
    minio_bucket: str = "translate-docs",
    minio_secure: bool = False,
    minio_prefix: str = "pdf2zh",
) -> StorageBackend:
    if backend == "minio":
        if not minio_endpoint:
            raise ValueError("MinIO 后端需要 PDF2ZH_MINIO_ENDPOINT")
        return MinioStorageBackend(
            endpoint=minio_endpoint,
            access_key=minio_access_key,
            secret_key=minio_secret_key,
            bucket=minio_bucket,
            secure=minio_secure,
            prefix=minio_prefix,
        )
    return LocalStorageBackend(local_root)

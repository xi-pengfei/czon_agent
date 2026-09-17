"""Create and restore encrypted migration backups."""
import hashlib
import json
import os
import shutil
import struct
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


_MAGIC = b"CZON_AGENT_BACKUP_V1\n"
_ITERATIONS = 600_000
_SALT_BYTES = 16
_NONCE_BYTES = 12
_TAG_BYTES = 16
_CHUNK_BYTES = 1024 * 1024
_BACKUP_ITEMS = (".env", "data", "skills", "uploads", "workspace")


def create_backup(project_root: Path, output_path: Path, password: str) -> Path:
    root = Path(project_root).resolve()
    output = Path(output_path).expanduser().resolve()
    _validate_password(password)
    _ensure_output_outside_data(output, root)
    output.parent.mkdir(parents=True, exist_ok=True)

    descriptor, temporary_name = tempfile.mkstemp(prefix=".czon-backup-", suffix=".zip", dir=output.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        manifest = _write_archive(root, temporary)
        _encrypt_file(temporary, output, password)
        try:
            output.chmod(0o600)
        except OSError:
            pass
        if not manifest["files"]:
            raise RuntimeError("没有找到可备份的数据")
        return output
    except Exception:
        output.unlink(missing_ok=True)
        raise
    finally:
        temporary.unlink(missing_ok=True)


def restore_backup(project_root: Path, backup_path: Path, password: str) -> None:
    root = Path(project_root).resolve()
    source = Path(backup_path).expanduser().resolve()
    _validate_password(password)
    if not source.is_file():
        raise RuntimeError(f"备份文件不存在：{source}")

    descriptor, temporary_name = tempfile.mkstemp(prefix=".czon-restore-", suffix=".zip", dir=root.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    staging = Path(tempfile.mkdtemp(prefix=".czon-restore-", dir=root.parent))
    rollback = Path(tempfile.mkdtemp(prefix=".czon-rollback-", dir=root.parent))
    replaced = []
    try:
        _decrypt_file(source, temporary, password)
        manifest = _extract_and_verify(temporary, staging)
        for name in manifest["items"]:
            incoming = staging / name
            if not incoming.exists():
                continue
            destination = root / name
            previous = rollback / name
            if destination.exists():
                previous.parent.mkdir(parents=True, exist_ok=True)
                os.replace(destination, previous)
            try:
                os.replace(incoming, destination)
                replaced.append(name)
            except OSError:
                if previous.exists():
                    os.replace(previous, destination)
                raise
    except Exception:
        for name in reversed(replaced):
            destination = root / name
            previous = rollback / name
            if destination.exists():
                _remove_path(destination)
            if previous.exists():
                os.replace(previous, destination)
        raise
    finally:
        temporary.unlink(missing_ok=True)
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(rollback, ignore_errors=True)


def _write_archive(root: Path, archive_path: Path) -> dict:
    files = []
    items = []
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in _BACKUP_ITEMS:
            source = root / name
            if not source.exists():
                continue
            items.append(name)
            if source.is_file():
                _add_file(archive, source, name, files)
                continue
            for current, directories, filenames in os.walk(source, followlinks=False):
                current_path = Path(current)
                for dirname in directories:
                    if (current_path / dirname).is_symlink():
                        raise RuntimeError(f"备份范围内不允许符号链接：{current_path / dirname}")
                for filename in filenames:
                    path = current_path / filename
                    if path.is_symlink():
                        raise RuntimeError(f"备份范围内不允许符号链接：{path}")
                    relative = path.relative_to(root).as_posix()
                    _add_file(archive, path, relative, files)
        manifest = {
            "format": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "items": items,
            "files": files,
        }
        archive.writestr("migration_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def _add_file(archive: zipfile.ZipFile, path: Path, relative: str, files: list) -> None:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_BYTES), b""):
            digest.update(chunk)
    archive.write(path, relative)
    files.append({"path": relative, "size": path.stat().st_size, "sha256": digest.hexdigest()})


def _extract_and_verify(archive_path: Path, staging: Path) -> dict:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            if "migration_manifest.json" not in names:
                raise RuntimeError("备份缺少迁移清单")
            manifest = json.loads(archive.read("migration_manifest.json"))
            if manifest.get("format") != 1 or not isinstance(manifest.get("files"), list):
                raise RuntimeError("备份格式不受支持")
            allowed = {item["path"] for item in manifest["files"]}
            if names - allowed - {"migration_manifest.json"}:
                raise RuntimeError("备份包含清单外文件")
            for item in manifest["files"]:
                relative = PurePosixPath(item["path"])
                if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                    raise RuntimeError("备份包含不安全路径")
                if relative.parts[0] not in _BACKUP_ITEMS:
                    raise RuntimeError("备份包含不受支持的目录")
                target = staging.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item["path"]) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                digest = _file_digest(target)
                if target.stat().st_size != item["size"] or digest != item["sha256"]:
                    raise RuntimeError(f"备份文件校验失败：{item['path']}")
            items = manifest.get("items")
            if not isinstance(items, list) or any(item not in _BACKUP_ITEMS for item in items):
                raise RuntimeError("备份项目清单不合法")
            return manifest
    except (zipfile.BadZipFile, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise RuntimeError("备份文件损坏或格式不正确") from exc


def _encrypt_file(source: Path, destination: Path, password: str) -> None:
    salt = os.urandom(_SALT_BYTES)
    nonce = os.urandom(_NONCE_BYTES)
    iterations = struct.pack(">I", _ITERATIONS)
    authenticated = _MAGIC + salt + nonce + iterations
    encryptor = Cipher(algorithms.AES(_derive_key(password, salt)), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(authenticated)
    with source.open("rb") as plain, destination.open("wb+") as encrypted:
        encrypted.write(authenticated)
        encrypted.write(b"\0" * _TAG_BYTES)
        for chunk in iter(lambda: plain.read(_CHUNK_BYTES), b""):
            encrypted.write(encryptor.update(chunk))
        encryptor.finalize()
        encrypted.seek(len(authenticated))
        encrypted.write(encryptor.tag)


def _decrypt_file(source: Path, destination: Path, password: str) -> None:
    with source.open("rb") as encrypted:
        magic = encrypted.read(len(_MAGIC))
        salt = encrypted.read(_SALT_BYTES)
        nonce = encrypted.read(_NONCE_BYTES)
        iterations = encrypted.read(4)
        tag = encrypted.read(_TAG_BYTES)
        if (
            magic != _MAGIC
            or len(salt) != _SALT_BYTES
            or len(nonce) != _NONCE_BYTES
            or len(iterations) != 4
            or len(tag) != _TAG_BYTES
        ):
            raise RuntimeError("不是有效的 czon_agent 迁移备份")
        count = struct.unpack(">I", iterations)[0]
        if count != _ITERATIONS:
            raise RuntimeError("备份加密参数不受支持")
        authenticated = magic + salt + nonce + iterations
        decryptor = Cipher(algorithms.AES(_derive_key(password, salt)), modes.GCM(nonce, tag)).decryptor()
        decryptor.authenticate_additional_data(authenticated)
        try:
            with destination.open("wb") as plain:
                for chunk in iter(lambda: encrypted.read(_CHUNK_BYTES), b""):
                    plain.write(decryptor.update(chunk))
                decryptor.finalize()
        except InvalidTag as exc:
            destination.unlink(missing_ok=True)
            raise RuntimeError("备份密码错误或文件已经损坏") from exc


def _derive_key(password: str, salt: bytes) -> bytes:
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=_ITERATIONS).derive(
        password.encode("utf-8")
    )


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_password(password: str) -> None:
    if len(password) < 6:
        raise RuntimeError("备份密码至少需要 6 位")


def _ensure_output_outside_data(output: Path, root: Path) -> None:
    for name in _BACKUP_ITEMS:
        source = root / name
        try:
            output.relative_to(source)
        except ValueError:
            continue
        raise RuntimeError(f"备份文件不能保存在 {name}/ 内")


def _remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)

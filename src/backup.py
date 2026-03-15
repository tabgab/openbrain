"""
Open Brain Backup & Restore
----------------------------
Creates a single AES-256-GCM encrypted archive containing:
  - Full PostgreSQL dump (memories + vault tables)
  - .env configuration file
  - Schema SQL for bare-metal restore

The archive is encrypted with a user-supplied password via PBKDF2-derived key.
File format (.obk):
  [16 bytes salt][12 bytes nonce][16 bytes GCM tag][...ciphertext of tar.gz...]
"""

import os
import io
import json
import tarfile
import tempfile
import datetime
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

# ---------------------------------------------------------------------------
# Encryption helpers
# ---------------------------------------------------------------------------

_KDF_ITERATIONS = 600_000  # OWASP recommended minimum for PBKDF2-SHA256

def _derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 256-bit AES key from a password using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_KDF_ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


def _encrypt(data: bytes, password: str) -> bytes:
    """Encrypt data with AES-256-GCM. Returns salt + nonce + tag + ciphertext."""
    salt = os.urandom(16)
    key = _derive_key(password, salt)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    # AESGCM.encrypt returns nonce || ciphertext || tag  — actually it returns ciphertext+tag
    ct_with_tag = aesgcm.encrypt(nonce, data, None)
    return salt + nonce + ct_with_tag


def _decrypt(blob: bytes, password: str) -> bytes:
    """Decrypt an encrypted blob. Raises on wrong password."""
    salt = blob[:16]
    nonce = blob[16:28]
    ct_with_tag = blob[28:]
    key = _derive_key(password, salt)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct_with_tag, None)


# ---------------------------------------------------------------------------
# Database dump / restore
# ---------------------------------------------------------------------------

def _dump_table_to_json(table: str) -> list[dict]:
    """Dump all rows of a table to a list of dicts (JSON-serializable)."""
    from db import get_connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM {table};")
        cols = [desc[0] for desc in cur.description]
        rows = []
        for row in cur.fetchall():
            record = {}
            for col, val in zip(cols, row):
                if col == "embedding" and val is not None:
                    record[col] = val.tolist() if hasattr(val, "tolist") else list(val)
                elif isinstance(val, datetime.datetime):
                    record[col] = val.isoformat()
                elif hasattr(val, "__str__") and not isinstance(val, (str, int, float, bool, list, dict, type(None))):
                    record[col] = str(val)
                else:
                    record[col] = val
            rows.append(record)
        return rows
    finally:
        conn.close()


def _restore_table_from_json(table: str, rows: list[dict], truncate: bool = True):
    """Restore rows into a table. Truncates existing data first by default."""
    if not rows:
        return 0
    from db import get_connection
    import numpy as np
    conn = get_connection()
    try:
        cur = conn.cursor()
        if truncate:
            cur.execute(f"TRUNCATE TABLE {table} CASCADE;")

        cols = list(rows[0].keys())
        placeholders = ", ".join(["%s"] * len(cols))
        col_names = ", ".join(cols)
        insert_sql = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING;"

        count = 0
        for row in rows:
            values = []
            for col in cols:
                val = row[col]
                if col == "embedding" and val is not None:
                    values.append(np.array(val))
                else:
                    values.append(val)
            cur.execute(insert_sql, values)
            count += 1

        conn.commit()
        return count
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------

# Keys that are excluded from .env when include_secrets=False
# DB password and vault are ALWAYS included.
_OPTIONAL_SECRET_KEYS = {"LLM_API_KEY", "TELEGRAM_BOT_TOKEN"}


def _filter_env(env_text: str, include_secrets: bool) -> str:
    """Optionally strip LLM API key and Telegram token from .env content."""
    if include_secrets:
        return env_text
    filtered_lines = []
    for line in env_text.splitlines(keepends=True):
        stripped = line.strip()
        # Skip lines that set an optional secret key
        key_part = stripped.split("=", 1)[0].strip() if "=" in stripped else ""
        if key_part in _OPTIONAL_SECRET_KEYS:
            filtered_lines.append(f"# {key_part}=  # excluded from backup\n")
        else:
            filtered_lines.append(line)
    return "".join(filtered_lines)


def create_backup(password: str, include_secrets: bool = True) -> tuple[bytes, dict]:
    """
    Create an encrypted .obk backup of the entire Open Brain system.
    
    Args:
        password: Encryption password.
        include_secrets: If False, LLM API key and Telegram bot token are
                         excluded from the .env in the backup. Database
                         password and vault secrets are always included.
    Returns (encrypted_bytes, metadata_dict).
    """
    project_root = os.path.dirname(os.path.dirname(__file__))
    tar_buffer = io.BytesIO()

    with tarfile.open(fileobj=tar_buffer, mode="w:gz") as tar:
        # 1. Database tables
        for table in ("memories", "vault"):
            try:
                rows = _dump_table_to_json(table)
                data = json.dumps(rows, ensure_ascii=False, default=str).encode("utf-8")
                info = tarfile.TarInfo(name=f"db/{table}.json")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            except Exception as e:
                print(f"[Backup] Warning: could not dump table '{table}': {e}", flush=True)

        # 2. .env configuration (optionally stripped of LLM/Telegram secrets)
        env_path = os.path.join(project_root, ".env")
        if os.path.exists(env_path):
            with open(env_path, "r") as ef:
                env_content = _filter_env(ef.read(), include_secrets)
            env_bytes = env_content.encode("utf-8")
            env_info = tarfile.TarInfo(name="config/.env")
            env_info.size = len(env_bytes)
            tar.addfile(env_info, io.BytesIO(env_bytes))

        # 3. Schema SQL (for bare restore)
        schema_path = os.path.join(project_root, "init-scripts", "schema.sql")
        if os.path.exists(schema_path):
            tar.add(schema_path, arcname="config/schema.sql")

        # 4. Manifest with metadata
        manifest = {
            "version": "1.0",
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "tables": ["memories", "vault"],
            "includes_env": os.path.exists(env_path),
            "includes_secrets": include_secrets,
            "includes_schema": os.path.exists(schema_path),
        }
        # Count rows
        try:
            manifest["memory_count"] = len(_dump_table_to_json("memories"))
        except Exception:
            manifest["memory_count"] = -1
        try:
            manifest["vault_count"] = len(_dump_table_to_json("vault"))
        except Exception:
            manifest["vault_count"] = -1

        manifest_data = json.dumps(manifest, indent=2).encode("utf-8")
        info = tarfile.TarInfo(name="manifest.json")
        info.size = len(manifest_data)
        tar.addfile(info, io.BytesIO(manifest_data))

    tar_bytes = tar_buffer.getvalue()
    encrypted = _encrypt(tar_bytes, password)

    return encrypted, manifest


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------

def restore_backup(encrypted_data: bytes, password: str) -> dict:
    """
    Restore an Open Brain system from an encrypted .obk backup.
    Returns a summary dict of what was restored.
    """
    # Decrypt
    try:
        tar_bytes = _decrypt(encrypted_data, password)
    except Exception:
        raise ValueError("Decryption failed — wrong password or corrupted backup file.")

    project_root = os.path.dirname(os.path.dirname(__file__))
    summary = {"tables_restored": [], "env_restored": False, "schema_restored": False}

    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
        # Read manifest
        try:
            manifest_member = tar.getmember("manifest.json")
            f = tar.extractfile(manifest_member)
            manifest = json.loads(f.read().decode("utf-8")) if f else {}
            summary["backup_version"] = manifest.get("version")
            summary["backup_created_at"] = manifest.get("created_at")
        except Exception:
            manifest = {}

        # Restore schema first (if present and database needs it)
        try:
            schema_member = tar.getmember("config/schema.sql")
            sf = tar.extractfile(schema_member)
            if sf:
                schema_sql = sf.read().decode("utf-8")
                from db import get_connection
                conn = get_connection()
                try:
                    cur = conn.cursor()
                    cur.execute(schema_sql)
                    conn.commit()
                    summary["schema_restored"] = True
                finally:
                    conn.close()
        except (KeyError, Exception) as e:
            print(f"[Restore] Schema restore skipped: {e}", flush=True)

        # Restore database tables
        for table in ("memories", "vault"):
            try:
                member = tar.getmember(f"db/{table}.json")
                f = tar.extractfile(member)
                if f:
                    rows = json.loads(f.read().decode("utf-8"))
                    count = _restore_table_from_json(table, rows, truncate=True)
                    summary["tables_restored"].append({"table": table, "rows": count})
            except KeyError:
                pass
            except Exception as e:
                summary["tables_restored"].append({"table": table, "error": str(e)})

        # Restore .env
        try:
            env_member = tar.getmember("config/.env")
            ef = tar.extractfile(env_member)
            if ef:
                env_path = os.path.join(project_root, ".env")
                env_content = ef.read()
                with open(env_path, "wb") as out:
                    out.write(env_content)
                summary["env_restored"] = True
        except KeyError:
            pass
        except Exception as e:
            summary["env_error"] = str(e)

    return summary

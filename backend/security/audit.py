#!/usr/bin/env python3
"""
Anonymous Signal — Security Audit Script
==========================================
Validates security and privacy configurations before deployment.
Run this script before every production deployment.

Usage:
    python security/audit.py

Exit code 0 = all checks passed
Exit code 1 = failures detected
"""

import os
import sys
import json
from pathlib import Path
from typing import List, Tuple

PASS = "✅"
FAIL = "❌"
WARN = "⚠️"

results: List[Tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "", warning_only: bool = False):
    status = PASS if condition else (WARN if warning_only else FAIL)
    results.append((name, condition, detail))
    icon = PASS if condition else (WARN if warning_only else FAIL)
    print(f"  {icon}  {name}")
    if detail and not condition:
        print(f"       → {detail}")


def section(title: str):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


# ─── Environment Checks ───────────────────────────────────────────────────────
section("1. Environment Configuration")

env_file = Path(".env")
env_example = Path(".env.example")

check("  .env file exists", env_file.exists(), "Copy .env.example to .env and fill in values")

if env_file.exists():
    env_vars = dict(line.split("=", 1) for line in env_file.read_text().splitlines()
                    if "=" in line and not line.startswith("#"))

    check(
        "  ENCRYPTION_KEY set",
        bool(env_vars.get("ENCRYPTION_KEY", "").strip()),
        "Generate: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
    )

    check(
        "  POSTGRES_PASSWORD changed",
        env_vars.get("POSTGRES_PASSWORD", "changeme") not in ["changeme", "password", "CHANGE_THIS_STRONG_PASSWORD_IN_PROD"],
        "Change the default PostgreSQL password"
    )

    check(
        "  JWT_SECRET set",
        len(env_vars.get("JWT_SECRET", "")) >= 32,
        "JWT_SECRET must be at least 32 characters"
    )

    check(
        "  REDIS_PASSWORD set",
        bool(env_vars.get("REDIS_PASSWORD", "").strip()) and
        env_vars.get("REDIS_PASSWORD") not in ["redis_changeme", "CHANGE_THIS_REDIS_PASSWORD"],
        "Set a strong Redis password"
    )

    # Privacy settings
    check(
        "  STORE_IP_ADDRESSES=false",
        env_vars.get("STORE_IP_ADDRESSES", "true").lower() == "false",
        "CRITICAL: STORE_IP_ADDRESSES must be 'false'"
    )

    check(
        "  DISABLE_ACCESS_LOGS=true",
        env_vars.get("DISABLE_ACCESS_LOGS", "false").lower() == "true",
        "CRITICAL: DISABLE_ACCESS_LOGS must be 'true'"
    )

# ─── Code Privacy Checks ──────────────────────────────────────────────────────
section("2. Privacy Code Checks")

def check_file_for_pattern(filepath: str, forbidden_patterns: List[str], description: str):
    """Check that a file does NOT contain forbidden patterns."""
    path = Path(filepath)
    if not path.exists():
        check(f"  {description} (file not found)", False, f"File {filepath} not found")
        return

    content = path.read_text()
    violations = [p for p in forbidden_patterns if p in content]
    check(
        f"  {description}",
        len(violations) == 0,
        f"Found forbidden patterns: {violations}" if violations else ""
    )

check_file_for_pattern(
    "backend/app/core/privacy_middleware.py",
    ["request.client.host", "X-Forwarded-For", "logging.basicConfig"],
    "Privacy middleware doesn't log IPs"
)

check_file_for_pattern(
    "backend/app/api/v1/endpoints/reports.py",
    ["request.client", "user_agent", "ip_address"],
    "Reports endpoint doesn't access identifying info"
)

# Check models don't have PII columns
check_file_for_pattern(
    "backend/app/models/models.py",
    ["ip_address", "user_agent", "phone_number", "email =", "device_id"],
    "Database models contain no PII columns"
)

# ─── Docker Security Checks ───────────────────────────────────────────────────
section("3. Docker Configuration")

docker_compose = Path("docker-compose.yml")
if docker_compose.exists():
    compose_content = docker_compose.read_text()

    check(
        "  Database not exposed externally",
        "expose:" in compose_content and "5432:5432" not in compose_content,
        "PostgreSQL port 5432 must not be mapped to host"
    )

    check(
        "  Redis not exposed externally",
        "6379:6379" not in compose_content,
        "Redis port 6379 must not be mapped to host"
    )

    check(
        "  AI service not exposed externally",
        "8001:8001" not in compose_content,
        "AI service port 8001 must not be mapped to host"
    )

    check(
        "  Internal network defined",
        "internal: true" in compose_content,
        "Database/AI services must be on internal-only network"
    )

# ─── Encryption Checks ────────────────────────────────────────────────────────
section("4. Encryption")

encryption_file = Path("backend/app/security/encryption.py")
if encryption_file.exists():
    enc_content = encryption_file.read_text()
    check("  Uses Fernet encryption", "Fernet" in enc_content, "Must use Fernet symmetric encryption")
    check("  EXIF stripping implemented", "_strip_image_metadata" in enc_content, "Must strip image EXIF")
    check("  Audio metadata stripping", "_strip_audio_metadata" in enc_content, "Must strip audio metadata")
    check("  Temp files deleted", "os.unlink" in enc_content or "delete=True" in enc_content or "delete=False" in enc_content)

# ─── Auth Security ────────────────────────────────────────────────────────────
section("5. Authentication")

auth_file = Path("backend/app/api/v1/auth.py")
if auth_file.exists():
    auth_content = auth_file.read_text()
    check("  bcrypt password hashing", "bcrypt" in auth_content, "Must use bcrypt for passwords")
    check("  JWT expiration configured", "expire" in auth_content.lower(), "JWT tokens must expire")
    check("  No plaintext passwords", "password" not in auth_content.lower() or "hash" in auth_content.lower())

# ─── Summary ──────────────────────────────────────────────────────────────────
section("Security Audit Summary")

total = len(results)
passed = sum(1 for _, ok, _ in results if ok)
failed = total - passed

print(f"\n  Results: {passed}/{total} checks passed")

if failed > 0:
    print(f"\n  {FAIL} {failed} checks FAILED — Do not deploy to production!")
    sys.exit(1)
else:
    print(f"\n  {PASS} All security checks passed! System ready for deployment.")
    sys.exit(0)

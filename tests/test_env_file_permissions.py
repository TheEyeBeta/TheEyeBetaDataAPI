"""bootstrap_local_env.py and rotate_secrets.py must never leave .env (or its
backups) group/other readable -- these files hold every runtime secret,
including ADMIN_ACCOUNT_APPROVAL_CODE.
"""

from __future__ import annotations

import glob
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_OWNER_RW_ONLY = stat.S_IRUSR | stat.S_IWUSR  # 0o600


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        [sys.executable, *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


def test_bootstrap_local_env_writes_env_as_owner_only(tmp_path: Path) -> None:
    shutil.copy(REPO_ROOT / ".env.example", tmp_path / ".env.example")
    script = REPO_ROOT / "scripts" / "bootstrap_local_env.py"

    _run(
        [str(script), "--database-url", "postgresql+psycopg://u:p@127.0.0.1:5432/db"],
        cwd=tmp_path,
    )

    env_path = tmp_path / ".env"
    assert env_path.exists()
    assert _mode(env_path) == _OWNER_RW_ONLY


def test_bootstrap_local_env_backup_is_owner_only(tmp_path: Path) -> None:
    shutil.copy(REPO_ROOT / ".env.example", tmp_path / ".env.example")
    script = REPO_ROOT / "scripts" / "bootstrap_local_env.py"

    _run(
        [str(script), "--database-url", "postgresql+psycopg://u:p@127.0.0.1:5432/db"],
        cwd=tmp_path,
    )
    # Second run with --force triggers the backup-then-overwrite path.
    _run(
        [str(script), "--database-url", "postgresql+psycopg://u:p@127.0.0.1:5432/db", "--force"],
        cwd=tmp_path,
    )

    backups = list(tmp_path.glob(".env.bak.*"))
    assert len(backups) == 1, f"expected exactly one backup, found {backups}"
    assert _mode(backups[0]) == _OWNER_RW_ONLY


def test_rotate_secrets_keeps_env_and_backup_owner_only(tmp_path: Path) -> None:
    shutil.copy(REPO_ROOT / ".env.example", tmp_path / ".env.example")
    bootstrap = REPO_ROOT / "scripts" / "bootstrap_local_env.py"
    _run(
        [str(bootstrap), "--database-url", "postgresql+psycopg://u:p@127.0.0.1:5432/db"],
        cwd=tmp_path,
    )

    # Loosen permissions first, the way a stray `cp`/editor save might, to
    # prove rotation actively re-tightens rather than merely preserving mode.
    env_path = tmp_path / ".env"
    os.chmod(env_path, 0o644)

    rotate = REPO_ROOT / "scripts" / "rotate_secrets.py"
    _run([str(rotate)], cwd=tmp_path)

    assert _mode(env_path) == _OWNER_RW_ONLY

    backups = glob.glob(str(tmp_path / ".env.bak.*"))
    assert len(backups) == 1, f"expected exactly one backup, found {backups}"
    # Regression check: with Path.with_suffix() this used to render as
    # ".env.env.bak.<timestamp>" because ".env" has no pathlib suffix.
    assert ".env.env.bak." not in backups[0]
    assert _mode(Path(backups[0])) == _OWNER_RW_ONLY

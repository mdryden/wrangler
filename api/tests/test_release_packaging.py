import subprocess
import sys
from pathlib import Path


def test_scripts_exist():
    root_dir = Path(__file__).resolve().parent.parent.parent
    prod_script = root_dir / "prod.ps1"
    release_script = root_dir / "release.ps1"
    assert prod_script.is_file()
    assert release_script.is_file()


def test_script_syntax_validation():
    if sys.platform != "win32":
        return

    root_dir = Path(__file__).resolve().parent.parent.parent
    for script_name in ("prod.ps1", "release.ps1"):
        script_path = root_dir / script_name
        parse_cmd = (
            f"$errors = $null; [System.Management.Automation.Language.Parser]::ParseFile("
            f"'{script_path.as_posix()}', [ref]$null, [ref]$errors); if ($errors) {{ throw $errors[0].Message }}"
        )
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            parse_cmd,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        assert proc.returncode == 0, f"{script_name} syntax error: {proc.stderr}"


def test_release_packaging_execution_and_isolation(tmp_path: Path):
    if sys.platform != "win32":
        return

    root_dir = Path(__file__).resolve().parent.parent.parent
    release_script = root_dir / "release.ps1"

    # Pre-create mock .env and data/test.db in target directory
    target_dir = tmp_path / "target_deployment"
    target_dir.mkdir(parents=True, exist_ok=True)
    env_file = target_dir / ".env"
    env_content = "DATA_DIR=custom_data_dir\nBACKUP_DIR=custom_backup_dir\n"
    env_file.write_text(env_content, encoding="utf-8")

    data_dir = target_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_file = data_dir / "test.db"
    db_content = "custom database binary/text content"
    db_file.write_text(db_content, encoding="utf-8")

    # Run release.ps1 with -SkipBuild targeting target_dir
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(release_script),
        "-TargetDir",
        str(target_dir),
        "-SkipBuild",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, f"release.ps1 failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"

    # Verify target contains expected files
    assert (target_dir / "api" / "src").is_dir()
    assert (target_dir / "api" / "alembic").is_dir()
    assert (target_dir / "api" / "scripts").is_dir()
    assert (target_dir / "web" / "dist").is_dir()
    assert (target_dir / "prod.ps1").is_file()

    # Verify pre-existing .env and data/test.db are completely untouched and unmodified
    assert env_file.is_file()
    assert env_file.read_text(encoding="utf-8") == env_content

    assert db_file.is_file()
    assert db_file.read_text(encoding="utf-8") == db_content

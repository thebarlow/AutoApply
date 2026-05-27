"""Cross-platform developer setup script."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

MIN_PYTHON = (3, 10)
ROOT = Path(__file__).parent
VENV_LINK = ROOT / ".venv"

# On WSL2/Linux: put the venv on the Linux filesystem to avoid 9P cross-boundary
# latency on imports. On Windows/Mac: use a local .venv as normal.
def _venv_root() -> Path:
    if sys.platform != "win32" and Path("/home").exists():
        home = Path.home()
        linux_venv = home / ".venvs" / ROOT.name
        if not VENV_LINK.exists():
            linux_venv.mkdir(parents=True, exist_ok=True)
            # We'll create the actual venv at the Linux path and symlink it
        return linux_venv
    return VENV_LINK


def _venv_python(venv: Path) -> Path:
    if sys.platform == "win32":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _run(*args: str, cwd: Path | None = None) -> None:
    result = subprocess.run(args, cwd=cwd)
    if result.returncode != 0:
        print(f"\n[setup] Command failed: {' '.join(args)}", file=sys.stderr)
        sys.exit(result.returncode)


def main() -> None:
    if sys.version_info < MIN_PYTHON:
        print(
            f"[setup] Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ required "
            f"(you have {sys.version_info.major}.{sys.version_info.minor})",
            file=sys.stderr,
        )
        sys.exit(1)

    venv = _venv_root()
    use_linux_venv = venv != VENV_LINK

    print(f"[setup] Creating virtual environment at {venv}...")
    # Use uv if available (much faster), fall back to stdlib venv
    if shutil.which("uv"):
        _run("uv", "venv", str(venv), "--python", sys.executable)
    else:
        _run(sys.executable, "-m", "venv", str(venv))

    if use_linux_venv and not VENV_LINK.exists():
        print(f"[setup] Symlinking .venv -> {venv}")
        VENV_LINK.symlink_to(venv)

    print("[setup] Installing dependencies...")
    python = str(_venv_python(venv))
    if shutil.which("uv"):
        _run("uv", "pip", "install", "-r", "requirements.txt", "--python", python)
    else:
        _run(python, "-m", "pip", "install", "-r", "requirements.txt")

    env_file = ROOT / ".env"
    env_example = ROOT / ".env.example"
    if not env_file.exists() and env_example.exists():
        shutil.copy(env_example, env_file)
        print("[setup] Created .env from .env.example")
        print("[setup] NOTE: Add your LLM API key via the Config tab after starting the server.")

    print("[setup] Installing Playwright browsers...")
    _run(python, "-m", "playwright", "install", "chromium")

    print("[setup] Initialising database...")
    _run(python, "-m", "db.init_db")

    dashboard = ROOT / "react-dashboard"
    npm = shutil.which("npm")
    if npm is None:
        print("\n[setup] WARNING: npm not found — skipping React dashboard build.")
        print("  Install Node.js from https://nodejs.org and re-run setup.py to build the UI.")
    else:
        print("[setup] Installing React dependencies...")
        _run(npm, "install", cwd=dashboard)
        print("[setup] Building React dashboard...")
        _run(npm, "run", "build", cwd=dashboard)

    activate = (
        r".venv\Scripts\activate" if sys.platform == "win32" else "source .venv/bin/activate"
    )
    print("\n[setup] Done. Next steps:")
    print(f"  {activate}")
    print("  start.bat  (Windows) — or: uvicorn web.main:app --host 0.0.0.0 --port 8080")
    print("  Open http://localhost:8080/")


if __name__ == "__main__":
    main()

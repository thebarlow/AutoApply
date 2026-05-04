"""Cross-platform developer setup script."""
import shutil
import subprocess
import sys
from pathlib import Path

MIN_PYTHON = (3, 10)
ROOT = Path(__file__).parent
VENV = ROOT / ".venv"


def _venv_python() -> Path:
    if sys.platform == "win32":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def _venv_pip() -> Path:
    if sys.platform == "win32":
        return VENV / "Scripts" / "pip.exe"
    return VENV / "bin" / "pip"


def _run(*args: str) -> None:
    result = subprocess.run(args)
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

    print("[setup] Creating virtual environment...")
    _run(sys.executable, "-m", "venv", str(VENV))

    print("[setup] Installing dependencies...")
    _run(str(_venv_pip()), "install", "-r", "requirements.txt")

    env_file = ROOT / ".env"
    env_example = ROOT / ".env.example"
    if not env_file.exists() and env_example.exists():
        shutil.copy(env_example, env_file)
        print("[setup] Created .env from .env.example")
        print("[setup] NOTE: Add your LLM API key via the Config tab after starting the server.")

    print("[setup] Initialising database...")
    _run(str(_venv_python()), "-m", "db.init_db")

    activate = (
        r".venv\Scripts\activate" if sys.platform == "win32" else "source .venv/bin/activate"
    )
    print("\n[setup] Done. Next steps:")
    print(f"  {activate}")
    print("  uvicorn web.main:app --reload")
    print("  Open http://127.0.0.1:8000/")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Start FoodLoop with one command: database, backend and website, in the right order.

    python run.py              set up anything missing, then start everything and open the browser
    python run.py --no-browser same, without opening the browser
    python run.py --setup      only set up (install, migrate, sample data), don't start

On Windows you can simply double-click "Start FoodLoop.bat" in this folder. Press Ctrl+C to stop.

The first run takes a few minutes (it installs the Python and JavaScript packages). After that it starts in
seconds. It never deletes anything and never touches your data: it only creates what's missing.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
WINDOWS = os.name == "nt"
VENV_PYTHON = BACKEND / ".venv" / ("Scripts/python.exe" if WINDOWS else "bin/python")
SITE = "http://localhost:5173"
API_HEALTH = "http://127.0.0.1:8000/api/health"


def say(text: str = "") -> None:
    print(text, flush=True)


def step(text: str) -> None:
    say(f"\n==> {text}")


def stop(problem: str, fix: str) -> None:
    say(f"\nPROBLEM: {problem}")
    say(f"FIX:     {fix}")
    sys.exit(1)


def run(command: list[str], cwd: Path, what: str) -> None:
    """Run a setup command, showing its output; stop with a clear message if it fails."""
    say("    $ " + " ".join(Path(part).name if i == 0 else part for i, part in enumerate(command)))
    if subprocess.run(command, cwd=cwd).returncode != 0:
        stop(f"{what} failed (see the messages above).", "Fix the problem shown above, then run FoodLoop again.")


def port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def fingerprint(*files: Path) -> str:
    digest = hashlib.sha256()
    for file in files:
        digest.update(file.read_bytes() if file.exists() else b"")
    return digest.hexdigest()


def read_env() -> dict[str, str]:
    values = {}
    for line in (BACKEND / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


# --------------------------------------------------------------------------------------------- checks

def check_tools() -> str:
    step("Checking Python and Node.js")
    if sys.version_info < (3, 12):
        stop(f"Python {sys.version.split()[0]} is too old.", "Install Python 3.12 or newer from python.org.")
    npm = shutil.which("npm")
    if not npm:
        stop("Node.js (npm) isn't installed or isn't on PATH.", "Install Node.js 22 LTS from nodejs.org, then open a new terminal.")
    say(f"    Python {sys.version.split()[0]}, npm found")
    return npm


def ensure_env_file() -> None:
    env = BACKEND / ".env"
    if not env.exists():
        step("Creating backend/.env from .env.example (your local settings)")
        shutil.copyfile(BACKEND / ".env.example", env)


def ensure_database() -> None:
    step("Checking the database")
    url = urlsplit(read_env().get("DATABASE_URL", "postgresql://localhost:5432/foodloop").replace("+psycopg", ""))
    host, port = url.hostname or "localhost", url.port or 5432
    host = "127.0.0.1" if host == "localhost" else host
    if port_open(host, port):
        say(f"    PostgreSQL is running on {host}:{port}")
        return
    docker = shutil.which("docker")
    if not docker or not (ROOT / "docker-compose.yml").exists():
        stop(f"PostgreSQL isn't running on {host}:{port}.",
             "Start your PostgreSQL service, or install Docker Desktop so FoodLoop can start it for you.")
    say("    PostgreSQL isn't running. Starting it with Docker (docker compose up -d)...")
    result = subprocess.run([docker, "compose", "up", "-d"], cwd=ROOT)
    if result.returncode != 0:
        stop("Docker couldn't start the database.",
             "Open Docker Desktop, wait until it says the engine is running, then run FoodLoop again.")
    for _ in range(60):
        if port_open(host, port):
            time.sleep(2)  # the port opens a moment before PostgreSQL accepts logins
            say("    PostgreSQL started")
            return
        time.sleep(1)
    stop("The database didn't start within a minute.", "Check Docker Desktop for errors, then run FoodLoop again.")


def ensure_backend() -> None:
    step("Preparing the backend (Python packages)")
    if not VENV_PYTHON.exists():
        say("    Creating the Python environment (backend/.venv)...")
        run([sys.executable, "-m", "venv", str(BACKEND / ".venv")], BACKEND, "Creating the Python environment")
    marker = BACKEND / ".venv" / ".foodloop-installed"
    wanted = fingerprint(BACKEND / "requirements.txt", BACKEND / "requirements-dev.txt")
    if not marker.exists() or marker.read_text() != wanted:
        say("    Installing Python packages (first run takes a minute or two)...")
        run([str(VENV_PYTHON), "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", "requirements-dev.txt"],
            BACKEND, "Installing Python packages")
        marker.write_text(wanted)
    else:
        say("    Python packages up to date")
    say("    Updating the database tables (alembic upgrade head)...")
    run([str(VENV_PYTHON), "-m", "alembic", "upgrade", "head"], BACKEND, "Updating the database tables")


def ensure_sample_data(enabled: bool) -> None:
    if not enabled or read_env().get("APP_ENV", "development") == "production":
        return
    step("Adding fresh sample meals (labelled “Sample data”)")
    run([str(VENV_PYTHON), "-m", "app.cli", "seed-sample", "--quiet"], BACKEND, "Adding sample meals")


def ensure_frontend(npm: str) -> None:
    step("Preparing the website (JavaScript packages)")
    marker = FRONTEND / "node_modules" / ".foodloop-installed"
    wanted = fingerprint(FRONTEND / "package.json", FRONTEND / "package-lock.json")
    if not marker.exists() or marker.read_text() != wanted:
        say("    Installing packages (npm install)...")
        run([npm, "install", "--no-audit", "--no-fund"], FRONTEND, "npm install")
        marker.write_text(wanted)
    else:
        say("    Packages up to date")


# ------------------------------------------------------------------------------------------- running

def stream(process: subprocess.Popen, label: str) -> None:
    assert process.stdout is not None
    for line in process.stdout:
        print(f"[{label}] {line.rstrip()}", flush=True)


def start(command: list[str], cwd: Path, label: str) -> subprocess.Popen:
    options: dict = {}
    if WINDOWS:
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                               encoding="utf-8", errors="replace", bufsize=1, **options)
    threading.Thread(target=stream, args=(process, label), daemon=True).start()
    return process


def end(process: subprocess.Popen) -> None:
    """Stop a server and everything it started (npm starts node, uvicorn --reload starts a worker)."""
    if process.poll() is not None:
        return
    if WINDOWS:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)], capture_output=True)
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def wait_until_up(url: str, seconds: int, processes: list[subprocess.Popen]) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if any(p.poll() is not None for p in processes):
            return False
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return True
        except OSError:
            pass
        time.sleep(1)
    return False


def serve(npm: str, open_browser: bool) -> None:
    for port, what in ((8000, "backend"), (5173, "website")):
        if port_open("127.0.0.1", port):
            stop(f"Port {port} is already in use, so the {what} can't start.",
                 f"FoodLoop may already be running: open {SITE}. Otherwise close the other window or program "
                 f"using port {port} (for example another FoodLoop folder), then run FoodLoop again.")
    step("Starting the backend and the website")
    api = start([str(VENV_PYTHON), "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"], BACKEND, "api")
    web = start([npm, "run", "dev", "--", "--port", "5173", "--strictPort"], FRONTEND, "web")
    processes = [api, web]
    try:
        if not wait_until_up(API_HEALTH, 60, processes):
            stop("The backend didn't start.", "Read the [api] messages above for the reason.")
        if not wait_until_up(SITE, 60, processes):
            stop("The website didn't start.", "Read the [web] messages above for the reason.")
        say("")
        say("=" * 64)
        say(f"  FoodLoop is running:  {SITE}")
        say("  Sample logins (password sample-pass-2024):")
        say("    customer@example.com   kitchen@example.com")
        say("  Press Ctrl+C in this window to stop FoodLoop.")
        say("=" * 64)
        if open_browser:
            webbrowser.open(SITE)
        while all(p.poll() is None for p in processes):
            time.sleep(1)
        say("\nOne of the servers stopped. Read the messages above for the reason.")
    except KeyboardInterrupt:
        say("\nStopping FoodLoop...")
    finally:
        for process in processes:
            end(process)
    say("FoodLoop stopped. Your data is safe in the database.")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="Set up and start FoodLoop.")
    parser.add_argument("--setup", action="store_true", help="only set up; don't start the servers")
    parser.add_argument("--no-browser", action="store_true", help="don't open the browser")
    parser.add_argument("--no-sample", action="store_true", help="don't add sample meals")
    args = parser.parse_args()

    say("FoodLoop: good food, less waste.")
    npm = check_tools()
    ensure_env_file()
    ensure_database()
    ensure_backend()
    ensure_sample_data(not args.no_sample)
    ensure_frontend(npm)
    if args.setup:
        say("\nSetup complete. Start FoodLoop with: python run.py")
        return
    serve(npm, not args.no_browser)


if __name__ == "__main__":
    main()

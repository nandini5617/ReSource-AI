"""Run:  python run_all_tests.py
Runs every offline test suite and the project audit, then prints one summary
line per suite plus the Python and Streamlit versions. No network, no API key."""
import subprocess
import sys

SUITES = [
    "test_offline.py",
    "test_exchange_safeguards.py",
    "test_vision.py",
    "test_stats.py",
    "test_explorer.py",
    "test_exchanges.py",
    "test_impact.py",
    "test_router_guard.py",
    "test_app.py",
    "audit_project.py",
]


def last_line(text: str) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    return lines[-1] if lines else "(no output)"


print("Python:", sys.version.split()[0])
try:
    import streamlit
    print("Streamlit:", streamlit.__version__)
except Exception as exc:  # noqa: BLE001
    print("Streamlit: not importable:", exc)
print()

failed = 0
for name in SUITES:
    try:
        proc = subprocess.run([sys.executable, name], capture_output=True,
                              text=True, timeout=300, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        failed += 1
        print(f"[TIMEOUT] {name}")
        continue
    ok = proc.returncode == 0
    failed += 0 if ok else 1
    summary = last_line(proc.stdout) if ok else last_line(proc.stderr or proc.stdout)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {summary}")

print(f"\n{len(SUITES) - failed}/{len(SUITES)} passed")
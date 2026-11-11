"""Run:  python audit_project.py
Read-only project audit: files, syntax, imports, secret scan, requirements."""
import os
import py_compile
import re
import sys
from pathlib import Path

os.environ["RESOURCE_AI_MOCK"] = "1"   # no cloud calls during the audit
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

SKIP_DIRS = {".git", "__pycache__", "venv", ".venv", "env", "node_modules",
             "data", "uploads", "outputs", ".idea", ".vscode"}
TEXT_EXT = {".py", ".md", ".txt", ".example", ".toml", ".json", ".yml", ".yaml", ".cfg", ".ini"}
SECRET_RE = re.compile(
    r"AIza[0-9A-Za-z_\-]{20,}|sk-ant-[A-Za-z0-9_\-]{8,}|sk-or-v1-[A-Za-z0-9]+|gsk_[A-Za-z0-9]+"
)
EXPECTED = [
    "config.py", "gemini_client.py", "ai_router.py", "knowledge.py", "impact.py",
    "database.py", "analysis.py", "matching.py", "memory.py", "tools.py",
    "agent.py", "main.py", "app.py", "test_offline.py",
    "test_exchange_safeguards.py", "requirements.txt", ".env.example",
]
MODULES = ["config", "knowledge", "impact", "database", "gemini_client", "ai_router",
           "analysis", "matching", "memory", "tools", "agent", "main"]

problems = 0


def report(ok, label):
    global problems
    if not ok:
        problems += 1
    print(f"  [{'ok' if ok else 'PROBLEM'}] {label}")


def project_files():
    for p in sorted(ROOT.rglob("*")):
        if p.is_file() and not (set(p.relative_to(ROOT).parts[:-1]) & SKIP_DIRS):
            yield p


print("\n1. Files in the project folder (data/, uploads/, outputs/ not listed)")
files = list(project_files())
for p in files:
    print("   ", p.relative_to(ROOT))

print("\n2. Expected files")
for name in EXPECTED:
    report((ROOT / name).exists(), f"{name} exists")
for name in ("README.md", "PROJECT_HANDOVER.md"):
    print(f"  [info] {name}: {'present' if (ROOT / name).exists() else 'not created yet'}")
print(f"  [info] .env present: {(ROOT / '.env').exists()} (contents are never read or shown)")
gi = ROOT / ".gitignore"
if gi.exists():
    text = gi.read_text(errors="ignore")
    report(".env" in text, ".gitignore lists .env")
else:
    print("  [info] no .gitignore (only matters if you ever share the folder or use git)")

print("\n3. Python syntax")
for p in files:
    if p.suffix == ".py":
        try:
            py_compile.compile(str(p), doraise=True)
            report(True, f"{p.name} compiles")
        except py_compile.PyCompileError as exc:
            report(False, f"{p.name}: {exc.msg.strip()[:150]}")

print("\n4. Module imports")
for m in MODULES:
    try:
        __import__(m)
        report(True, f"import {m}")
    except Exception as exc:  # noqa: BLE001
        report(False, f"import {m}: {type(exc).__name__}: {str(exc)[:120]}")

print("\n5. Hard-coded API key scan (file names and line numbers only)")
hits = 0
for p in files:
    if p.name == ".env" or p.suffix not in TEXT_EXT:
        continue
    for n, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
        if SECRET_RE.search(line):
            hits += 1
            print(f"  [PROBLEM] possible key in {p.relative_to(ROOT)} line {n}")
report(hits == 0, "no key-like strings found in project files")

print("\n6. requirements.txt")
req = ROOT / "requirements.txt"
if req.exists():
    content = req.read_text(errors="ignore").lower()
    for pkg in ("streamlit", "google-genai", "groq", "openai", "python-dotenv"):
        report(pkg in content, f"requirements lists {pkg}")

print("\n7. AI-exposed tool safety")
try:
    import tools
    declared = {d["name"] for d in tools.TOOL_DECLARATIONS}
    exposed = [n for n in declared | set(tools._HANDLERS)
               if n.startswith(("confirm_", "reject_", "cancel_exchange"))]
    report(not exposed, "user-only exchange functions are not exposed to the AI")
    upd = next(d for d in tools.TOOL_DECLARATIONS if d["name"] == "update_exchange_status")
    report(upd["parameters"]["properties"]["status"]["enum"] == ["cancelled"],
           "AI tool offers only 'cancelled'")
except Exception as exc:  # noqa: BLE001
    report(False, f"safety check could not run: {exc}")

print("\n8. Possibly unused provider files")
for name in ("groq_client.py", "openrouter_client.py"):
    f = ROOT / name
    if f.exists():
        stem = f.stem
        used_by = [p.name for p in files if p.suffix == ".py" and p != f
                   and re.search(rf"\b(import|from)\s+{stem}\b", p.read_text(errors="ignore"))]
        print(f"  [info] {name}: imported by {used_by or 'nothing (not used by the app)'}")

print(f"\nAUDIT FINISHED: {problems} problem(s) found")
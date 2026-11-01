"""
verify_lab5.py — швидка перевірка, що робота зібрана правильно.

Запускається ЗА СЕКУНДИ і не викликає агента: перевіряє середовище,
файли, конфіги й те, що зламаний проєкт справді зламаний саме так, як
задумано. Запускайте перед тим, як братися за довгі заміри.

    python verify_lab5.py

API-КЛЮЧІ: не потрібні.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT / "project"

GREEN, RED, DIM, OFF = "\033[32m", "\033[31m", "\033[90m", "\033[0m"


class Check:
    def __init__(self):
        self.bad = []

    def __call__(self, ok, title, detail=""):
        mark = f"{GREEN}ok {OFF}" if ok else f"{RED}НІ {OFF}"
        print(f"  {mark} {title}")
        if detail:
            print(f"       {DIM}{detail}{OFF}")
        if not ok:
            self.bad.append(title)
        return ok


def strip_jsonc(text):
    """Прибрати // коментарі. Рядків із // усередині значень тут немає."""
    out = []
    for line in text.splitlines():
        cut = line.find("//")
        if cut >= 0 and line[:cut].count('"') % 2 == 0:
            line = line[:cut]
        out.append(line)
    return "\n".join(out)


def pytest_counts(cwd):
    with tempfile.TemporaryDirectory() as tmp:
        xml = Path(tmp) / "r.xml"
        subprocess.run([sys.executable, "-m", "pytest", "-q", "--tb=no",
                        f"--junit-xml={xml}"],
                       cwd=cwd, capture_output=True, text=True)
        if not xml.exists():
            return None
        s = ET.parse(xml).getroot()
        if s.tag == "testsuites":
            s = s[0]
        total = int(s.get("tests", 0))
        bad = (int(s.get("failures", 0)) + int(s.get("errors", 0))
               + int(s.get("skipped", 0)))
        return total - bad, total


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    print("=" * 68)
    print("  ПЕРЕВІРКА ЛАБОРАТОРНОЇ 5")
    print("=" * 68)
    c = Check()

    # ── середовище ───────────────────────────────────────────────────
    print("\n── середовище ──")
    v = sys.version_info
    c(v >= (3, 10), f"Python {v.major}.{v.minor}.{v.micro}",
      "потрібен 3.10 або новіший")

    oc = shutil.which("opencode") or shutil.which("opencode.cmd")
    ver = ""
    if oc:
        p = subprocess.run([oc, "--version"], capture_output=True, text=True)
        ver = (p.stdout or "").strip().splitlines()[0] if p.stdout else ""
    c(bool(oc), f"opencode у PATH {ver}",
      "немає → npm i -g opencode-ai")

    try:
        import pytest                                    # noqa: F401
        c(True, "pytest встановлено")
    except ImportError:
        c(False, "pytest встановлено", "pip install -r requirements.txt")

    # ── файли ────────────────────────────────────────────────────────
    print("\n── файли ──")
    need = ["bench.py", "probe.py", "opencode.jsonc",
            "project/analytics.py", "project/test_analytics.py",
            "configs/deny_shell.jsonc", "configs/deny_bash_broken.jsonc",
            "configs/mcp_store.jsonc"]
    for rel in need:
        c((ROOT / rel).exists(), rel)

    # ── конфіги ──────────────────────────────────────────────────────
    print("\n── конфіги ──")
    for rel in ("opencode.jsonc", "configs/deny_shell.jsonc",
                "configs/deny_bash_broken.jsonc", "configs/mcp_store.jsonc"):
        path = ROOT / rel
        if not path.exists():
            continue
        try:
            data = json.loads(strip_jsonc(path.read_text(encoding="utf-8")))
            c(True, f"{rel} — валідний JSONC")
        except json.JSONDecodeError as exc:
            c(False, f"{rel} — валідний JSONC", str(exc))
            continue
        if rel.endswith("mcp_store.jsonc"):
            srv = data.get("mcp", {}).get("servers", {})
            c(bool(srv), "mcp.servers заповнено",
              "у 2.x сервери саме тут, не під mcp.<ім'я>")
            for name, body in srv.items():
                c(body.get("type") in ("local", "remote"),
                  f"server «{name}»: type = {body.get('type')!r}",
                  'дозволено лише "local" або "remote"; "stdio" не існує')
                cmd = body.get("command")
                c(isinstance(cmd, list) and len(cmd) >= 2,
                  f"server «{name}»: command — масив",
                  "файл і аргументи одним масивом, окремого args немає")
                if isinstance(cmd, list):
                    c(not any("{env:" in str(x) for x in cmd),
                      f"server «{name}»: без {{env:…}} у command",
                      "з ним запуск зависає")
                    c(all(Path(x).exists() for x in cmd if "/" in str(x)
                          or "\\" in str(x)),
                      f"server «{name}»: шляхи існують",
                      "підставте свої шляхи до ЛР4")

    # ── пастка ───────────────────────────────────────────────────────
    print("\n── пастка з дозволами ──")
    broken = ROOT / "configs/deny_bash_broken.jsonc"
    if broken.exists():
        data = json.loads(strip_jsonc(broken.read_text(encoding="utf-8")))
        acts = [p.get("action") for p in data.get("permissions", [])]
        c(acts == ["bash"], "deny_bash_broken.jsonc досі містить дію bash",
          "саме вона й не існує — у цьому суть пастки")

    real = ROOT / "configs/deny_shell.jsonc"
    if real.exists():
        data = json.loads(strip_jsonc(real.read_text(encoding="utf-8")))
        rules = data.get("permissions", [])
        c(any(r.get("action") == "shell" and r.get("effect") == "deny"
              for r in rules),
          "deny_shell.jsonc забороняє shell")

    # ── зламаний проєкт ──────────────────────────────────────────────
    print("\n── зламаний проєкт ──")
    res = pytest_counts(PROJECT)
    if res is None:
        c(False, "pytest запускається в project/")
    else:
        passed, total = res
        c(total == 4, f"тестів у наборі: {total}", "має бути 4")
        c(passed == 1, f"проходить зараз: {passed} з {total}",
          "має бути рівно 1 — якщо більше, проєкт уже полагоджено: "
          "git checkout -- project/")

    src = (PROJECT / "analytics.py").read_text(encoding="utf-8")
    c("sold={}" in src.replace(" ", ""),
      "вада 1 на місці: мутабельний аргумент за замовчуванням")
    c(re.search(r"start\s*<\s*o\[.date.\]\s*<\s*end", src) is not None,
      "вада 2 на місці: межі проміжку виключно")
    c("mean(monthly.values())" in src,
      "вада 3 на місці: середнє від середніх")

    tests = (PROJECT / "test_analytics.py").read_text(encoding="utf-8")
    c("ЗМІНЮВАТИ НЕ МОЖНА" in tests,
      "у тестах є застереження не правити їх")

    # ── підсумок ─────────────────────────────────────────────────────
    print("\n" + "=" * 68)
    if c.bad:
        print(f"  ПРОБЛЕМ: {len(c.bad)}")
        for b in c.bad:
            print(f"    · {b}")
        print("=" * 68)
        return 1
    print("  Усе на місці. Далі:")
    print("    python probe.py --all      — перевірити дозволи")
    print("    python bench.py --repeat 2 — заміряти моделі")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
Тести самої обв'язки — не того проєкту, який лагодить агент.

Жоден із них не викликає агента й не ходить у мережу, тож набір
проходить за секунди й годиться для CI.

    pytest -q tests/
"""
import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PROJECT = ROOT / "project"

sys.path.insert(0, str(ROOT))
import bench                                            # noqa: E402
import verify_lab5                                      # noqa: E402


# ────────────────────────── зламаний проєкт ──────────────────────────
def test_project_starts_broken():
    """Рівно один тест із чотирьох має проходити на старті."""
    passed, total, _ = bench.run_pytest()
    assert total == 4, f"у наборі {total} тестів замість 4"
    assert passed == 1, (
        f"проходить {passed} з {total}; проєкт має бути зламаний — "
        "git checkout -- project/")


def test_each_planted_bug_is_actually_a_bug():
    """
    Три вади мусять бути справжніми, а не косметичними: виправляємо
    кожну окремо в копії модуля й перевіряємо, що відповідний тест
    починає проходити.
    """
    src = (PROJECT / "analytics.py").read_text(encoding="utf-8")
    fixes = [
        ("start < o[\"date\"] < end", "start <= o[\"date\"] <= end"),
        ("return round(mean(monthly.values()), 2)",
         "return round(revenue(orders) / len(orders), 2)"),
        ("def top_products(orders, limit=3, sold={}):",
         "def top_products(orders, limit=3, sold=None):\n"
         "    sold = {} if sold is None else sold"),
    ]
    for old, new in fixes:
        assert src.count(old) == 1, f"не знайшов у коді: {old!r}"
        src = src.replace(old, new)

    ns = {}
    exec(compile(src, "analytics_fixed", "exec"), ns)       # noqa: S102
    sys.path.insert(0, str(PROJECT))
    import test_analytics as t                              # noqa: E402

    orders = t.ORDERS
    assert len(ns["orders_in_period"](orders, "2026-01-10", "2026-02-28")) == 5
    assert ns["average_check"](orders) == 8720.00
    assert ns["top_products"](orders) == ns["top_products"](orders)


# ─────────────────────────── знімок і відкат ─────────────────────────
def test_restore_brings_files_back(tmp_path):
    """Відкат мусить повернути змінений файл."""
    files, _ = bench.snapshot()
    target = PROJECT / "analytics.py"
    original = target.read_bytes()
    try:
        target.write_bytes(b"# zzz\n")
        assert target.read_bytes() != original
        bench.restore(files)
        assert target.read_bytes() == original
    finally:
        target.write_bytes(original)


def test_restore_survives_deleted_file():
    """
    Агент може не зіпсувати файл, а ВИДАЛИТИ його. Наївне відновлення,
    яке спершу читає файл для порівняння, падає тут із
    FileNotFoundError, і наступний замір іде по зіпсованому проєкту.
    """
    files, _ = bench.snapshot()
    target = PROJECT / "analytics.py"
    original = target.read_bytes()
    try:
        target.unlink()
        assert not target.exists()
        bench.restore(files)
        assert target.exists()
        assert target.read_bytes() == original
    finally:
        target.write_bytes(original)


def test_restore_removes_files_the_agent_added():
    files, _ = bench.snapshot()
    extra = PROJECT / "agent_leftover.py"
    try:
        extra.write_text("# сміття після агента\n", encoding="utf-8")
        bench.restore(files)
        assert not extra.exists()
    finally:
        if extra.exists():
            extra.unlink()


# ──────────────────────────── евристика слів ─────────────────────────
@pytest.mark.parametrize("text", [
    "All tests pass now.",
    "Fixed the bug in analytics.py",
    "The issue has been resolved.",
    "Successfully updated the module.",
])
def test_success_words_detected(text):
    assert bench.SUCCESS_WORDS.search(text)


@pytest.mark.parametrize("text", [
    "I could not find the problem.",
    "Three tests are still failing.",
    "",
])
def test_success_words_not_detected(text):
    assert not bench.SUCCESS_WORDS.search(text)


# ───────────────────────────── конфіги ───────────────────────────────
def _load(name):
    raw = (ROOT / name).read_text(encoding="utf-8")
    return json.loads(verify_lab5.strip_jsonc(raw))


@pytest.mark.parametrize("name", [
    "opencode.jsonc",
    "configs/deny_shell.jsonc",
    "configs/deny_bash_broken.jsonc",
    "configs/mcp_store.jsonc",
])
def test_configs_are_valid_jsonc(name):
    _load(name)


def test_mcp_config_uses_2x_layout():
    """У 1.x сервери лежали під mcp.<ім'я> — старий приклад мовчки
    не спрацює, тож перевіряємо саме mcp.servers.<ім'я>."""
    cfg = _load("configs/mcp_store.jsonc")
    servers = cfg["mcp"]["servers"]
    assert servers, "mcp.servers порожній"
    for name, body in servers.items():
        assert body["type"] in ("local", "remote"), \
            f'{name}: type={body["type"]!r}; "stdio" не існує'
        assert isinstance(body["command"], list), \
            f"{name}: command має бути масивом"
        assert not any("{env:" in str(x) for x in body["command"]), \
            f"{name}: {{env:…}} у command підвішує запуск"


def test_broken_config_still_names_a_nonexistent_action():
    """
    Пастка має сенс, лише доки дії bash справді немає. Якщо вона
    з'явиться у новій версії OpenCode, цей тест нагадає оновити
    матеріали.
    """
    cfg = _load("configs/deny_bash_broken.jsonc")
    assert [p["action"] for p in cfg["permissions"]] == ["bash"]

    oc = _opencode()
    if oc is None:
        pytest.skip("opencode не встановлено")
    proc = subprocess.run([oc, "debug", "agents"], cwd=ROOT,
                          capture_output=True, text=True, timeout=120)
    if proc.returncode != 0 or not proc.stdout.strip():
        pytest.skip("opencode debug agents нічого не повернув")
    actions = {p["action"] for ag in json.loads(proc.stdout)
               for p in ag.get("permissions", [])}
    assert "bash" not in actions, (
        "дія bash з'явилася в OpenCode — пастка більше не пастка, "
        "оновіть configs/deny_bash_broken.jsonc і методичку")


def _opencode():
    import shutil
    return shutil.which("opencode") or shutil.which("opencode.cmd")


# ──────────────────────────── цілісність ─────────────────────────────
def test_no_api_keys_anywhere():
    """
    У роботі не має бути ні ключів, ні місць, де їх просять.

    Себе цей файл не перевіряє: шукані маркери написані просто нижче,
    інакше тест ловив би сам себе.
    """
    here = Path(__file__).resolve()
    suspicious = []
    for path in ROOT.rglob("*"):
        if (not path.is_file() or ".venv" in path.parts
                or ".git" in path.parts or "__pycache__" in path.parts
                or path.resolve() == here):
            continue
        if path.suffix not in (".py", ".jsonc", ".json", ".md", ".txt"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in ("sk-ant-", "sk-proj-", "OPENAI_API_KEY",
                       "ANTHROPIC_API_KEY"):
            if marker in text:
                suspicious.append(f"{path.name}: {marker}")
    assert not suspicious, suspicious


def test_every_script_parses():
    for name in ("bench.py", "probe.py", "verify_lab5.py"):
        ast.parse((ROOT / name).read_text(encoding="utf-8"), filename=name)

"""Run every test file without needing pytest:  python tests/run_all.py"""
import importlib.util
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
failed = total = 0
for name in sorted(f for f in os.listdir(os.path.join(ROOT, "tests")) if f.startswith("test_") and f.endswith(".py")):
    spec = importlib.util.spec_from_file_location(name[:-3], os.path.join(ROOT, "tests", name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for test in [getattr(module, n) for n in dir(module) if n.startswith("test_") and callable(getattr(module, n)) and getattr(getattr(module, n), "__module__", "") == name[:-3]]:
        total += 1
        try:
            from tests.conftest_env import fresh_db
            fresh_db()
            test()
            print("PASS", name, test.__name__)
        except Exception:  # noqa: BLE001
            failed += 1
            print("FAIL", name, test.__name__)
            traceback.print_exc()
print(f"\n{total - failed}/{total} tests passed")
sys.exit(1 if failed else 0)

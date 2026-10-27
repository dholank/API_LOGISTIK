import json
import platform
import sys
import tomllib
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    manifest = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    python_pin = (root / ".python-version").read_text(encoding="utf-8").strip()
    driver_pin = next(
        item.removeprefix("oracledb==")
        for item in manifest["project"]["dependencies"]
        if item.startswith("oracledb==")
    )

    try:
        import oracledb
    except ImportError:
        print(json.dumps({"ok": False, "error": "oracledb_not_installed"}))
        return 1

    checks = {
        "python_version": platform.python_version() == python_pin,
        "manifest_python_pin": manifest["project"]["requires-python"] == f"=={python_pin}",
        "project_virtualenv": Path(sys.prefix).resolve() == (root / ".venv").resolve(),
        "driver_version": oracledb.__version__ == driver_pin,
        "thin_mode": oracledb.is_thin_mode(),
    }
    ok = all(checks.values())
    print(
        json.dumps(
            {
                "ok": ok,
                "python": platform.python_version(),
                "oracledb": oracledb.__version__,
                "checks": checks,
                "database_connection_tested": False,
            },
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

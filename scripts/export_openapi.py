import argparse
import json
from pathlib import Path

from api_logistik.config import Settings
from api_logistik.main import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the installed API schema without Oracle.")
    parser.add_argument("output", nargs="?", type=Path, default=Path("docs/openapi.json"))
    args = parser.parse_args()

    # Trusted constants bypass BaseSettings environment sources and dotenv loading.
    settings = Settings.model_construct(
        environment="test",
        docs_enabled=True,
        oracle_dsn=None,
        oracle_user=None,
        oracle_password=None,
        oracle_writer_user=None,
        oracle_writer_password=None,
        oracle_wallet_dir=None,
        oracle_wallet_password=None,
        oracle_mode="thin",
        oracle_client_lib_dir=None,
        key_secret_store_dir=None,
        key_encryption_key=None,
        key_encryption_key_file=None,
        operator_authorized=False,
    )
    schema = create_app(settings).openapi()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(schema, ensure_ascii=False, indent=2) + "\n"
    args.output.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()

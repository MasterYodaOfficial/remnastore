from __future__ import annotations

import argparse

import uvicorn

from app.core.logging import configure_logging


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the RemnaStore API server.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--reload-dir", action="append", dest="reload_dirs", default=[])
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()
    configure_logging(component_name="api")
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        reload_dirs=args.reload_dirs or None,
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    main()

import argparse
from pathlib import Path

from . import store
from .runner import configure, export
from .scenarios import FAMILIES


def main():
    parser = argparse.ArgumentParser(description="FAULTLINE: execute a reproducible recovery lab")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=0)
    run = sub.add_parser("run")
    run.add_argument("--output", type=Path, default=Path("artifacts/demo"))
    run.add_argument("--seeds", type=int, nargs="+", default=[17])
    run.add_argument("--model", default=None)
    run.add_argument("--attempts", type=int, default=1)
    run.add_argument("--size", type=int, default=12)
    args = parser.parse_args()
    configure()
    store.initialize()
    if args.command == "serve":
        from .service import serve as start
        start(args.port)
    else:
        if not 1 <= args.attempts <= 5 or len(args.seeds) > 20:
            parser.error("maximum 5 attempts and 20 seeds per command")
        result = export(args.output, args.seeds, model=args.model, attempts=args.attempts, size=args.size)
        if result["failures"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()

import argparse
import json
from pathlib import Path

from .generate import generate
from .pipeline import analyze, json_default


def main():
    parser = argparse.ArgumentParser(description="Reconcile ad-request events and review publisher yield.")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="Generate the synthetic fixture and its reports")
    demo.add_argument("--data", type=Path, default=Path("data/generated"))
    demo.add_argument("--output", type=Path, default=Path("reports"))
    demo.add_argument("--requests-per-day", type=int, default=5000)
    demo.add_argument("--seed", type=int, default=20261120)
    review = sub.add_parser("analyze", help="Analyze a compatible local CSV export")
    review.add_argument("--data", type=Path, required=True)
    review.add_argument("--output", type=Path, default=Path("local-results"))
    review.add_argument("--as-of", help="UTC-offset timestamp overriding the report cutoff")
    args = parser.parse_args()
    if args.command == "demo":
        generate(args.data, requests_per_day=args.requests_per_day, seed=args.seed)
    summary = analyze(args.data, args.output, as_of=getattr(args, "as_of", None))
    print(json.dumps({k: summary[k] for k in ["requests", "mature_comparison", "overall_bridge", "quality"]},
                     default=json_default, indent=2))


if __name__ == "__main__":
    main()

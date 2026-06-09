from __future__ import annotations

import argparse
from pathlib import Path
import sys

from app.graph import ShoppingAssistant


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Shopping Assistant Multi-Agent CLI.")
    parser.add_argument("--question", help="Run one question through the graph.")
    parser.add_argument("--test-file", default="data/test.json")
    parser.add_argument("--trace-file", default=None)
    parser.add_argument("--batch", action="store_true")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild the policy index.")
    parser.add_argument("--output-dir", default="src/artifacts/traces", help="Output directory for traces.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    assistant = ShoppingAssistant()
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.batch:
        test_file = Path(args.test_file)
        if not test_file.exists():
            # Try absolute path relative to root
            test_file = assistant.settings.root_dir / args.test_file
            
        print(f"Running batch tests from {test_file}...")
        summary = assistant.run_batch(
            test_file=test_file,
            output_dir=output_dir,
            rebuild_index=args.rebuild
        )
        print("\nBatch test completed.")
        print(f"Total: {summary['total']}")
        print(f"Results saved to {output_dir}")
        
    elif args.question:
        trace_file = Path(args.trace_file) if args.trace_file else output_dir / "single_trace.json"
        
        print(f"Question: {args.question}")
        result = assistant.ask(
            question=args.question,
            trace_file=trace_file,
            rebuild_index=args.rebuild
        )
        
        print("-" * 50)
        print(result["final_answer"])
        print("-" * 50)
        print(f"Trace saved to {trace_file}")
    else:
        build_parser().print_help()


if __name__ == "__main__":
    main()

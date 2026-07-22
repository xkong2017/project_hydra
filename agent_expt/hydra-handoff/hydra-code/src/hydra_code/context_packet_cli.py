"""CLI entry point for context packet generation."""
from __future__ import annotations

import argparse
from pathlib import Path

from .context_packet import generate_context_packet


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate HydraCode context packet")
    parser.add_argument("--task", required=True, help="Task description")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="Repository root")
    parser.add_argument("--output", type=Path, default=None, help="Output file path")
    parser.add_argument("--base-sha", default="HEAD", help="Base git SHA")
    parser.add_argument("--branch", default="", help="Branch name")
    parser.add_argument("--acceptance-criteria", nargs="*", help="Acceptance criteria")
    parser.add_argument("--constraints", nargs="*", help="Constraints")

    args = parser.parse_args()

    packet = generate_context_packet(
        task=args.task,
        repo_root=args.repo,
        base_sha=args.base_sha,
        branch=args.branch or "",
        acceptance_criteria=args.acceptance_criteria,
        constraints=args.constraints,
    )

    if args.output:
        args.output.write_text(packet)
        print(f"Context packet written to {args.output}")
    else:
        print(packet)


if __name__ == "__main__":
    main()

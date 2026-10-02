from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from gltest.bench import BenchmarkResult, BenchmarkRunner


def _json_list(value: str, *, option: str) -> list[Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"{option} must be valid JSON") from exc
    if not isinstance(parsed, list):
        raise argparse.ArgumentTypeError(f"{option} must be a JSON array")
    return parsed


def _run_direct(
    contract_path: Path,
    method_name: str,
    constructor_args: list[Any],
    method_args: list[Any],
    iterations: int,
    warmup_iterations: int,
) -> BenchmarkResult:
    from gltest.direct import VMContext, deploy_contract

    vm = VMContext()
    with vm.activate():
        contract = deploy_contract(contract_path, vm, *constructor_args)
        try:
            method = getattr(contract, method_name)
        except AttributeError as exc:
            raise ValueError(f"Contract has no method '{method_name}'") from exc

        operation = lambda: method(*method_args)
        return BenchmarkRunner(operation, mode="direct").run(
            iterations=iterations,
            warmup_iterations=warmup_iterations,
        )


def _run_studio(
    contract_path: Path,
    method_name: str,
    constructor_args: list[Any],
    method_args: list[Any],
    iterations: int,
    warmup_iterations: int,
) -> BenchmarkResult:
    from gltest import get_contract_factory

    factory = get_contract_factory(contract_file_path=contract_path)
    contract = factory.deploy(args=constructor_args)

    try:
        method_factory = getattr(contract, method_name)
    except AttributeError as exc:
        raise ValueError(f"Contract has no method '{method_name}'") from exc

    contract_function = method_factory(args=method_args)
    operation = (
        contract_function.call
        if contract_function.read_only
        else contract_function.transact
    )
    return BenchmarkRunner(operation, mode="studio").run(
        iterations=iterations,
        warmup_iterations=warmup_iterations,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gltest bench",
        description=(
            "Benchmark an Intelligent Contract method. Deployment is excluded "
            "from measured samples."
        ),
    )
    parser.add_argument("contract", type=Path, help="Path to the contract Python file")
    parser.add_argument("--method", required=True, help="Contract method to benchmark")
    parser.add_argument(
        "--mode",
        choices=("direct", "studio"),
        default="direct",
        help="Execution path to measure (default: direct)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=100,
        help="Measured executions (default: 100)",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=3,
        help="Unmeasured warmup executions (default: 3)",
    )
    parser.add_argument(
        "--constructor-args",
        default="[]",
        metavar="JSON",
        help='Constructor arguments as a JSON array (default: "[]")',
    )
    parser.add_argument(
        "--args",
        default="[]",
        metavar="JSON",
        help='Method arguments as a JSON array (default: "[]")',
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON",
    )
    parser.add_argument(
        "--include-samples",
        action="store_true",
        help="Include per-iteration latency samples in JSON output",
    )
    return parser


def _format_human(result: BenchmarkResult) -> str:
    return "\n".join(
        [
            f"Mode: {result.mode}",
            f"Iterations: {result.iterations} (+{result.warmup_iterations} warmup)",
            f"Mean latency: {result.mean_ms:.3f} ms",
            f"Median latency: {result.median_ms:.3f} ms",
            f"P95 latency: {result.p95_ms:.3f} ms",
            f"Min / max: {result.min_ms:.3f} / {result.max_ms:.3f} ms",
            f"Throughput: {result.throughput_ops_s:.2f} ops/s",
            f"CPU time: {result.cpu_time_ms:.3f} ms",
            f"Peak process RSS: {result.process_rss_peak_mb:.2f} MiB",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.iterations <= 0:
        parser.error("--iterations must be greater than zero")
    if args.warmup < 0:
        parser.error("--warmup cannot be negative")
    if not args.contract.is_file():
        parser.error(f"contract file not found: {args.contract}")

    constructor_args = _json_list(args.constructor_args, option="--constructor-args")
    method_args = _json_list(args.args, option="--args")

    runner = _run_direct if args.mode == "direct" else _run_studio
    result = runner(
        args.contract,
        args.method,
        constructor_args,
        method_args,
        args.iterations,
        args.warmup,
    )

    if args.json:
        print(
            json.dumps(
                result.as_dict(include_samples=args.include_samples),
                sort_keys=True,
            )
        )
    else:
        print(_format_human(result))
    return 0

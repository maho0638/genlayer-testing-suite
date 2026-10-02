import json
import sys

from gltest.bench import BenchmarkResult
import gltest_cli.bench as bench_cli
import gltest_cli.main as cli_main


def _result(mode="direct"):
    return BenchmarkResult(
        mode=mode,
        iterations=2,
        warmup_iterations=1,
        total_ms=4.0,
        mean_ms=2.0,
        median_ms=2.0,
        p95_ms=3.0,
        min_ms=1.0,
        max_ms=3.0,
        throughput_ops_s=500.0,
        cpu_time_ms=1.0,
        process_rss_peak_mb=42.0,
        samples_ms=(1.0, 3.0),
    )


def test_gltest_keeps_forwarding_non_bench_args_to_pytest(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["gltest", "-q", "tests/gltest/"])
    seen = {}

    def fake_pytest_main():
        seen["called"] = True
        return 7

    monkeypatch.setattr(cli_main.pytest, "main", fake_pytest_main)

    assert cli_main.main() == 7
    assert seen == {"called": True}


def test_gltest_dispatches_bench_subcommand(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["gltest", "bench", "contract.py", "--method", "ping"],
    )
    seen = {}

    def fake_bench_main(argv):
        seen["argv"] = argv
        return 0

    monkeypatch.setattr(bench_cli, "main", fake_bench_main)

    assert cli_main.main() == 0
    assert seen["argv"] == ["contract.py", "--method", "ping"]


def test_bench_json_output_and_arguments(monkeypatch, tmp_path, capsys):
    contract = tmp_path / "Contract.py"
    contract.write_text("# contract")
    seen = {}

    def fake_run(
        contract_path,
        method_name,
        constructor_args,
        method_args,
        iterations,
        warmup_iterations,
    ):
        seen.update(
            contract_path=contract_path,
            method_name=method_name,
            constructor_args=constructor_args,
            method_args=method_args,
            iterations=iterations,
            warmup_iterations=warmup_iterations,
        )
        return _result()

    monkeypatch.setattr(bench_cli, "_run_direct", fake_run)

    rc = bench_cli.main(
        [
            str(contract),
            "--method",
            "ping",
            "--iterations",
            "2",
            "--warmup",
            "1",
            "--constructor-args",
            "[1]",
            "--args",
            "[\"hello\"]",
            "--json",
            "--include-samples",
        ]
    )

    assert rc == 0
    assert seen == {
        "contract_path": contract,
        "method_name": "ping",
        "constructor_args": [1],
        "method_args": ["hello"],
        "iterations": 2,
        "warmup_iterations": 1,
    }
    payload = json.loads(capsys.readouterr().out)
    assert payload["p95_ms"] == 3.0
    assert payload["samples_ms"] == [1.0, 3.0]


def test_bench_selects_studio_adapter(monkeypatch, tmp_path):
    contract = tmp_path / "Contract.py"
    contract.write_text("# contract")
    seen = {}

    def fake_run(*args):
        seen["args"] = args
        return _result(mode="studio")

    monkeypatch.setattr(bench_cli, "_run_studio", fake_run)

    assert (
        bench_cli.main(
            [
                str(contract),
                "--method",
                "ping",
                "--mode",
                "studio",
                "--iterations",
                "2",
            ]
        )
        == 0
    )
    assert seen["args"][1] == "ping"

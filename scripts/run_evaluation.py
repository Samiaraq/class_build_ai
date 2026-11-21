
import argparse
import json
import socket
import unittest
import ipaddress
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from scripts.evaluation_scenarios import SCENARIOS


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RecordingResult(unittest.TestResult):
    """Records the outcome and reason for every executed test."""

    def __init__(self):
        super().__init__()
        self.outcomes = {}

    @staticmethod
    def _test_id(test):
        return test.id()

    def addSuccess(self, test):
        super().addSuccess(test)
        self.outcomes[self._test_id(test)] = {
            "status": "passed",
            "reason": "Test passed.",
        }

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.outcomes[self._test_id(test)] = {
            "status": "failed",
            "reason": self._exc_info_to_string(err, test),
        }

    def addError(self, test, err):
        super().addError(test, err)
        self.outcomes[self._test_id(test)] = {
            "status": "error",
            "reason": self._exc_info_to_string(err, test),
        }

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.outcomes[self._test_id(test)] = {
            "status": "skipped",
            "reason": reason,
        }

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self.outcomes[self._test_id(test)] = {
                "status": "failed",
                "reason": self._exc_info_to_string(err, test),
            }


@contextmanager
def block_network():
    """Block external network connections while allowing local connections."""

    def is_loopback(address):
        if isinstance(address, tuple) and address:
            host = address[0]

            if isinstance(host, str) and host.lower() == "localhost":
                return True

            try:
                return ipaddress.ip_address(host).is_loopback
            except ValueError:
                return False

        return False

    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_create_connection = socket.create_connection

    def guarded_connect(sock, address, *args, **kwargs):
        if is_loopback(address):
            return original_connect(sock, address, *args, **kwargs)

        raise OSError("Network access is disabled during evaluation.")

    def guarded_connect_ex(sock, address, *args, **kwargs):
        if is_loopback(address):
            return original_connect_ex(sock, address, *args, **kwargs)

        raise OSError("Network access is disabled during evaluation.")

    def guarded_create_connection(address, *args, **kwargs):
        if is_loopback(address):
            return original_create_connection(address, *args, **kwargs)

        raise OSError("Network access is disabled during evaluation.")

    from unittest.mock import patch

    with (
        patch.object(socket.socket, "connect", guarded_connect),
        patch.object(socket.socket, "connect_ex", guarded_connect_ex),
        patch.object(socket, "create_connection", guarded_create_connection),
    ):
        yield


def _flatten_suite(suite):
    """Return all individual test cases inside a test suite."""

    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from _flatten_suite(test)
        else:
            yield test


def load_tests(test_ids):
    """Load each test ID and collect tests that could not be found."""

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    load_errors = {}

    for test_id in test_ids:
        try:
            loaded = loader.loadTestsFromName(test_id)
            cases = list(_flatten_suite(loaded))

            failed_cases = [
                case for case in cases
                if case.__class__.__name__ == "_FailedTest"
            ]

            if failed_cases:
                error = getattr(
                    failed_cases[0],
                    "_exception",
                    "Test could not be loaded.",
                )
                load_errors[test_id] = str(error)
                continue

            if not cases:
                load_errors[test_id] = "No test was found."
                continue

            suite.addTests(cases)

        except Exception as exc:
            load_errors[test_id] = str(exc)

    return suite, load_errors


def evaluate():
    """Run all scenario tests once and build the evaluation report."""

    test_ids = [
        test_id
        for scenario in SCENARIOS
        for test_id in scenario.tests
    ]

    suite, load_errors = load_tests(test_ids)
    result = RecordingResult()

    with block_network():
        suite.run(result)

    scenarios_report = []

    for scenario in SCENARIOS:
        test_results = []

        for test_id in scenario.tests:
            outcome = result.outcomes.get(test_id)

            if test_id in load_errors:
                outcome = {
                    "status": "load_error",
                    "reason": load_errors[test_id],
                }

            if outcome is None:
                outcome = {
                    "status": "not_run",
                    "reason": "Test did not run.",
                }

            test_results.append({
                "test_id": test_id,
                **outcome,
            })

        tests_passed = sum(
            item["status"] == "passed"
            for item in test_results
        )

        scenario_passed = all(
            item["status"] == "passed"
            for item in test_results
        )

        scenarios_report.append({
            "number": scenario.number,
            "name": scenario.name,
            "category": scenario.category,
            "checks": scenario.checks,
            "tests_total": len(test_results),
            "tests_passed": tests_passed,
            "passed": scenario_passed,
            "tests": test_results,
        })

    total_tests = sum(
        item["tests_total"] for item in scenarios_report
    )
    passed_tests = sum(
        item["tests_passed"] for item in scenarios_report
    )
    total_scenarios = len(scenarios_report)
    passed_scenarios = sum(
        item["passed"] for item in scenarios_report
    )

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": {
            "total_scenarios": total_scenarios,
            "passed_scenarios": passed_scenarios,
            "failed_scenarios": total_scenarios - passed_scenarios,
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "pass_percentage": (
                round(passed_tests / total_tests * 100, 2)
                if total_tests else 0
            ),
        },
        "scenarios": scenarios_report,
    }


def short(test_id):
    """Return a shorter test name for console output."""

    return test_id.removeprefix("tests.")


def print_report(report):
    """Print scenarios grouped by category."""

    print("\n" + "=" * 72)
    print("MINI CLASSBUILD - EVALUATION REPORT")
    print("=" * 72)

    summary = report["summary"]

    print(
        f"\nScenarios: {summary['passed_scenarios']}/"
        f"{summary['total_scenarios']} passed"
    )
    print(
        f"Tests:     {summary['passed_tests']}/"
        f"{summary['total_tests']} passed"
    )
    print(f"Pass rate: {summary['pass_percentage']}%")

    categories = {}

    for scenario in report["scenarios"]:
        categories.setdefault(scenario["category"], []).append(scenario)

    for category, scenarios in categories.items():
        print(f"\n--- {category} ---")

        for scenario in scenarios:
            status = "PASS" if scenario["passed"] else "FAIL"

            print(
                f"[{status}] {scenario['number']:02d}. "
                f"{scenario['name']} "
                f"({scenario['tests_passed']}/"
                f"{scenario['tests_total']} tests)"
            )

            for test in scenario["tests"]:
                if test["status"] != "passed":
                    print(
                        f"    - {test['status'].upper()}: "
                        f"{short(test['test_id'])}"
                    )
                    print(f"      {test['reason'].splitlines()[0]}")

    print("\n" + "=" * 72)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run Mini ClassBuild evaluation scenarios."
    )
    parser.add_argument(
        "--no-json",
        action="store_true",
        help="Print the report without saving JSON files.",
    )
    parser.add_argument(
        "--output-dir",
        default="evaluation_results",
        help="Directory for JSON evaluation reports.",
    )

    args = parser.parse_args(argv)

    report = evaluate()
    print_report(report)

    if not args.no_json:
        output_dir = PROJECT_ROOT / args.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

        report_path = output_dir / f"evaluation-{timestamp}.json"
        latest_path = output_dir / "latest.json"

        report_text = json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        )

        report_path.write_text(report_text, encoding="utf-8")
        latest_path.write_text(report_text, encoding="utf-8")

        print(f"\nReports saved to: {output_dir}")

    return 0 if report["summary"]["failed_scenarios"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

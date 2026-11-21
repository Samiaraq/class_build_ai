
import argparse
import importlib.metadata
import importlib.util
import os
import re
import subprocess
import sys
import time

from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_FILE = PROJECT_ROOT / "requirements.txt"


@dataclass
class CheckResult:
    name: str
    passed: bool
    summary: str
    details: str = ""


def parse_requirements(path):
    """Read package names and minimum versions from requirements.txt."""

    requirements = []

    if not path.exists():
        return requirements

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line or line.startswith("#"):
            continue

        match = re.match(
            r"^([A-Za-z0-9_.-]+)\s*(?:>=\s*([0-9.]+))?",
            line,
        )

        if match:
            name = match.group(1)
            minimum_version = match.group(2)
            requirements.append((name, minimum_version))

    return requirements


def child_environment():
    """Create a safe environment for offline checks."""

    environment = os.environ.copy()
    environment["GROQ_API_KEY"] = ""
    environment["HF_HUB_OFFLINE"] = "1"

    return environment


def run(command):
    """Run a command from the project root with a timeout."""

    started = time.perf_counter()

    try:
        process = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            env=child_environment(),
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )

        output = process.stdout + process.stderr
        return process.returncode, output, time.perf_counter() - started

    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "")
        if isinstance(output, bytes):
            output = output.decode(errors="replace")

        return 1, output + "\nCommand timed out.", time.perf_counter() - started

    except OSError as exc:
        return 1, str(exc), time.perf_counter() - started


def _version_tuple(version):
    """Convert a version string into comparable numeric parts."""

    numbers = re.findall(r"\d+", version)
    return tuple(int(number) for number in numbers)


def check_python():
    """Check that the project is running on Python 3.11 or newer."""

    version = sys.version_info
    passed = version >= (3, 11)

    summary = (
        f"Python {version.major}.{version.minor}.{version.micro}"
        if passed
        else "Python 3.11 or newer is required."
    )

    return CheckResult(
        name="Python version",
        passed=passed,
        summary=summary,
    )


def check_dependencies():
    """Check that requirements are installed and importable."""

    if not REQUIREMENTS_FILE.exists():
        return CheckResult(
            name="Dependencies",
            passed=False,
            summary="requirements.txt was not found.",
        )

    requirements = parse_requirements(REQUIREMENTS_FILE)
    problems = []

    import_names = {
        "python-dotenv": "dotenv",
        "sentence-transformers": "sentence_transformers",
    }

    for package, minimum_version in requirements:
        try:
            installed_version = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            problems.append(f"{package}: not installed.")
            continue

        if minimum_version:
            if (
                _version_tuple(installed_version)
                < _version_tuple(minimum_version)
            ):
                problems.append(
                    f"{package}: {installed_version} is below "
                    f"the required {minimum_version}."
                )
                continue

        module_name = import_names.get(
            package,
            package.replace("-", "_"),
        )

        try:
            available = importlib.util.find_spec(module_name) is not None
        except (ImportError, ValueError):
            available = False

        if not available:
            problems.append(f"{package}: import '{module_name}' failed.")

    passed = not problems

    return CheckResult(
        name="Dependencies",
        passed=passed,
        summary=(
            f"All {len(requirements)} requirements are installed."
            if passed
            else f"{len(problems)} dependency problem(s) found."
        ),
        details="\n".join(problems),
    )


def _command_check(name, command, success_summary):
    """Run a command and convert its result into a CheckResult."""

    code, output, duration = run(command)

    passed = code == 0

    summary = (
        f"{success_summary} ({duration:.1f}s)"
        if passed
        else f"Command failed with exit code {code} ({duration:.1f}s)."
    )

    return CheckResult(
        name=name,
        passed=passed,
        summary=summary,
        details=output,
    )


def check_unit_tests():
    """Run the complete unittest suite."""

    return _command_check(
        "Unit tests",
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-t",
            ".",
            "-v",
        ],
        "Unit tests passed",
    )

def check_evaluation():
    """Run the evaluation scenarios without creating JSON files."""

    return _command_check(
        "Evaluation",
        [
            sys.executable,
            "-m",
            "scripts.run_evaluation",
            "--no-json",
        ],
        "Evaluation passed",
    )


def check_end_to_end():
    """Run the end-to-end workflow test."""

    return _command_check(
        "End-to-end test",
        [
            sys.executable,
            "-m",
            "unittest",
            "tests.test_end_to_end",
            "-v",
        ],
        "End-to-end test passed",
    )


CHECKS = [
    ("Python version", check_python, False),
    ("Dependencies", check_dependencies, False),
    ("Unit tests", check_unit_tests, True),
    ("Evaluation", check_evaluation, True),
    ("End-to-end test", check_end_to_end, True),
]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run the final offline checks for Mini ClassBuild."
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show full command output for each check.",
    )

    args = parser.parse_args(argv)

    results = []
    dependencies_available = False

    print("\nMINI CLASSBUILD - FINAL CHECK")
    print("=" * 60)

    for name, check_function, needs_dependencies in CHECKS:

        if needs_dependencies and not dependencies_available:
            result = CheckResult(
                name=name,
                passed=False,
                summary="Skipped because dependencies are unavailable.",
            )

        else:
            result = check_function()

        if name == "Dependencies":
            dependencies_available = result.passed

        results.append(result)

        status = "PASS" if result.passed else "FAIL"

        print(f"\n[{status}] {result.name}")
        print(f"  {result.summary}")

        if args.verbose and result.details:
            print("\n" + result.details)

    passed_count = sum(result.passed for result in results)
    total_count = len(results)

    print("\n" + "=" * 60)
    print(f"FINAL RESULT: {passed_count}/{total_count} checks passed")

    if passed_count == total_count:
        print("All final checks passed.")
    else:
        print("Some checks failed. Review the details above.")

    return 0 if passed_count == total_count else 1


if __name__ == "__main__":
    raise SystemExit(main())

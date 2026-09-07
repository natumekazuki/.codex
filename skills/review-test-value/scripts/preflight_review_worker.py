"""Report deterministic readiness without making a model call."""
from __future__ import annotations

import argparse
from extract_test_values import canonical_json
from review_worker import prepare_worker
from validate_review_result import CONTRACT_VERSION, ReviewError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", required=True)
    parser.add_argument("--role-file", required=True)
    args = parser.parse_args(argv)
    try:
        preparation = prepare_worker(cli=args.cli, role_file=args.role_file)
        result = {"contract_version": CONTRACT_VERSION, "ready": True,
                  "identity": preparation["identity"], "llm_calls": 0,
                  "requested_model": preparation["role"]["model"],
                  "requested_effort": preparation["role"]["model_reasoning_effort"],
                  "runtime_e2e": "NOT_RUN"}
        code = 0
    except ReviewError as exc:
        result = {"contract_version": CONTRACT_VERSION, "ready": False,
                  "llm_calls": 0, "failure": exc.diagnostic()}
        code = 2
    print(canonical_json(result))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

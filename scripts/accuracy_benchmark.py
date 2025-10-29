#!/usr/bin/env python3
"""
Benchmark harness for DocAutomate extraction accuracy.

Usage:
    python scripts/accuracy_benchmark.py --dataset datasets/benchmark.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from ingester import DocumentIngester
from extractor import ActionExtractor


@dataclass
class BenchmarkCase:
    path: Path
    expected_fields: Dict[str, str]
    document_type: Optional[str] = None


async def evaluate_case(
    ingester: DocumentIngester,
    extractor: ActionExtractor,
    case: BenchmarkCase,
) -> Dict[str, float]:
    document = await ingester.ingest_file(str(case.path))
    doc_type = case.document_type or (document.metadata or {}).get("document_type")
    actions = await extractor.extract_actions(document.text, document_type=doc_type)

    extracted_fields: Dict[str, str] = {}
    for action in actions:
        for entity in action.entities:
            extracted_fields[entity.name] = str(entity.value)

    expected = case.expected_fields
    matched = sum(1 for key, value in expected.items() if extracted_fields.get(key) == value)
    total = len(expected)
    accuracy = matched / total if total else 0.0

    return {
        "document_id": document.id,
        "matched": matched,
        "total": total,
        "accuracy": accuracy,
        "delegation_status": document.delegation_status,
    }


async def run_benchmark(dataset_path: Path) -> None:
    cases = []
    payload = json.loads(dataset_path.read_text())
    for entry in payload:
        cases.append(
            BenchmarkCase(
                path=dataset_path.parent / entry["path"],
                expected_fields=entry.get("expected", {}),
                document_type=entry.get("document_type"),
            )
        )

    ingester = DocumentIngester()
    extractor = ActionExtractor()

    results: List[Dict[str, float]] = []
    for case in cases:
        result = await evaluate_case(ingester, extractor, case)
        results.append(result)

    if not results:
        print("No benchmark cases found.")
        return

    aggregate_accuracy = sum(r["accuracy"] for r in results) / len(results)
    print(f"Processed {len(results)} documents. Average accuracy: {aggregate_accuracy:.2%}")
    for result in results:
        print(
            f"- {result['document_id']}: accuracy {result['accuracy']:.2%} "
            f"(matched {result['matched']} of {result['total']} fields, delegation={result['delegation_status']})"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="DocAutomate accuracy benchmark harness")
    parser.add_argument("--dataset", type=Path, required=True, help="Path to benchmark dataset JSON")
    args = parser.parse_args()

    if not args.dataset.exists():
        raise SystemExit(f"Dataset file not found: {args.dataset}")

    asyncio.run(run_benchmark(args.dataset))


if __name__ == "__main__":
    main()

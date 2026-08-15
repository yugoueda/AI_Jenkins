#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def parse_lcov(path: Path) -> dict:
    total_lines = hit_lines = total_branches = hit_branches = 0
    uncovered: dict[str, list[int]] = {}
    current_file = ""

    for line in path.read_text().splitlines():
        if line.startswith("SF:"):
            current_file = line[3:]
            uncovered.setdefault(current_file, [])
        elif line.startswith("DA:"):
            line_number, hits, *_ = line[3:].split(",")
            total_lines += 1
            if int(hits) > 0:
                hit_lines += 1
            elif current_file:
                uncovered[current_file].append(int(line_number))
        elif line.startswith("BRDA:"):
            *_, hits = line[5:].split(",")
            total_branches += 1
            if hits != "-" and int(hits) > 0:
                hit_branches += 1

    return {
        "c0": hit_lines * 100 / total_lines if total_lines else 100.0,
        "c1": hit_branches * 100 / total_branches if total_branches else 100.0,
        "uncovered_lines": {
            file_path: lines for file_path, lines in uncovered.items() if lines
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    print(json.dumps(parse_lcov(args.path), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

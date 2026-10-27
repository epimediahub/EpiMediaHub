#!/usr/bin/env python3
"""Create a reviewed 512 MiB relay-budget candidate without touching production."""
import argparse
import ast
from pathlib import Path

OLD = "MAX_INPUT_BYTES = 128 * 1024 * 1024"
NEW = "MAX_INPUT_BYTES = 512 * 1024 * 1024"


def patch(text):
    if text.count(OLD) != 1:
        raise ValueError("UNRECOGNIZED_PROVIDER_BUDGET")
    updated = text.replace(OLD, NEW, 1)
    ast.parse(updated)
    return updated


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("Output must differ from source")
    args.output.write_text(patch(args.source.read_text()))
    print("512_MIB_CANDIDATE_CREATED; NOT_DEPLOYED")


if __name__ == "__main__":
    main()

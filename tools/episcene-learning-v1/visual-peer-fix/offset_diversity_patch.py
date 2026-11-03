#!/usr/bin/env python3
"""Fail-closed source patch for EpiScene visual offset candidate selection.

The current detector ranks all fingerprint time-shifts and examines only
the best twelve. Several nearby shifts from a single peak can crowd out
alternative repeat positions. Preserve the vote threshold, 12-candidate
budget and every later visual/audio release rule; diversify shifts FIRST,
then backfill from the original ranking.

This module NEVER writes a production file or approves a marker.
Import patch(source) and apply to a staged copy only after an A/B replay.
"""
from __future__ import annotations

import ast
import re

EXPECTED = ast.parse(
    "sorted(np.flatnonzero(votes >= max(15, 15000 // target.step_ms)), "
    "key=lambda i: int(votes[i]), reverse=True)",
    mode="eval",
).body

def _node_signature(node):
    return ast.dump(node, include_attributes=False)

def patch(source: str) -> tuple[str, bool]:
    """Return patched text; fail on unknown source shape or duplicate targets."""
    tree = ast.parse(source)
    matches = [
        n for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "_pair_candidates"
    ]
    if len(matches) != 1:
        raise ValueError("Expected exactly one top-level _pair_candidates")
    fn = matches[0]
    offsets = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Assign)
        and len(n.targets) == 1
        and isinstance(n.targets[0], ast.Name)
        and n.targets[0].id == "offsets"
    ]
    if len(offsets) != 1:
        raise ValueError("Unrecognized offsets assignment count")
    stmt = offsets[0]
    # This variant must not be re-applied or silently override another patch.
    if not (isinstance(stmt.value, ast.Subscript)
            and isinstance(stmt.value.slice, ast.Slice)
            and stmt.value.slice.lower is None
            and stmt.value.slice.step is None
            and isinstance(stmt.value.slice.upper, ast.Constant)
            and stmt.value.slice.upper.value == 12
            and _node_signature(stmt.value.value) == _node_signature(EXPECTED)):
        raise ValueError("Offset ranking changed: refusing unknown detector code")
    lines = source.splitlines(keepends=True)
    first = lines[stmt.lineno - 1]
    prefix = re.match(r"^([ \t]*)offsets[ \t]*=", first)
    if not prefix:
        raise ValueError("Unexpected indentation or offsets assignment")
    indent = prefix.group(1)
    # 2,000 ms separation for initial peaks, never below 2 samples. This does
    # NOT loosen the per-frame match, 15-second, 90%-ratio or consensus gates.
    body = [
        "ranked_offsets = " + ast.unparse(stmt.value.value),
        "offsets = []",
        "min_shift_separation = max(2, 2000 // target.step_ms)",
        "for proposed_offset in ranked_offsets:",
        "    if len(offsets) >= 12:",
        "        break",
        "    if all(abs(int(proposed_offset) - int(existing)) >= min_shift_separation",
        "           for existing in offsets):",
        "        offsets.append(proposed_offset)",
        "if len(offsets) < 12:",
        "    selected_offsets = {int(x) for x in offsets}",
        "    for proposed_offset in ranked_offsets:",
        "        if len(offsets) >= 12:",
        "            break",
        "        if int(proposed_offset) not in selected_offsets:",
        "            offsets.append(proposed_offset)",
        "            selected_offsets.add(int(proposed_offset))",
    ]
    # AST source locations identify the exact multi-line assignment to replace.
    # Convert relative block indentation to function-level indentation.
    rendered = []
    for line in body:
        if line and line[0] != " ":
            rendered.append(indent + line + "\n")
        else:
            rendered.append(indent + line + "\n")
    updated = lines[:stmt.lineno - 1] + rendered + lines[stmt.end_lineno:]
    result = "".join(updated)
    new_tree = ast.parse(result)
    compile(result, "<visual-offset-diversity>", "exec")

    # Only the body of _pair_candidates may differ.
    old_other = [_node_signature(n) for n in tree.body
                 if not (isinstance(n, ast.FunctionDef)
                         and n.name == "_pair_candidates")]
    new_other = [_node_signature(n) for n in new_tree.body
                 if not (isinstance(n, ast.FunctionDef)
                         and n.name == "_pair_candidates")]
    if old_other != new_other:
        raise ValueError("Unexpected change outside visual pair candidates")
    return result, result != source

if __name__ == "__main__":
    raise SystemExit("Import patch(source). This helper never modifies a file.")

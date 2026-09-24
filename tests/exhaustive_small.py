#!/usr/bin/env python3
"""Independent exhaustive oracle for small deletion-and-projection instances.

This file intentionally does not import the producer or certificate consumer.
It enumerates subsequences directly and compares them with an independently
implemented dynamic-programming LCS recurrence.  It also checks projection
monotonicity and exact unit-cost interface selection on every three-trace
instance over a two-bit, two-row universe.
"""
from __future__ import annotations

import argparse
import itertools
import json
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Sequence

Word = tuple[int, ...]


def project(word: Word, mask: int) -> Word:
    return tuple(symbol & mask for symbol in word)


@lru_cache(maxsize=None)
def subsequences_exact(word: Word, length: int) -> frozenset[Word]:
    if length < 0 or length > len(word):
        return frozenset()
    return frozenset(tuple(word[i] for i in indices)
                     for indices in itertools.combinations(range(len(word)), length))


def collides_by_enumeration(left: Word, right: Word, deletion_budget: int) -> bool:
    threshold = len(left) - deletion_budget
    if len(left) != len(right) or threshold < 0:
        raise ValueError("equal nonnegative lengths and a valid budget are required")
    return bool(subsequences_exact(left, threshold) & subsequences_exact(right, threshold))


def lcs_grid(left: Sequence[int], right: Sequence[int]) -> int:
    previous = [0] * (len(right) + 1)
    for a in left:
        current = [0]
        for j, b in enumerate(right, 1):
            if a == b:
                current.append(previous[j - 1] + 1)
            else:
                current.append(max(previous[j], current[-1]))
        previous = current
    return previous[-1]


def words(alphabet_size: int, length: int) -> Iterable[Word]:
    return itertools.product(range(alphabet_size), repeat=length)


def check_collision_theorem() -> dict[str, int]:
    configurations = [(1, 4), (2, 3), (3, 2)]
    word_pairs = projected_checks = theorem_checks = monotonicity_checks = 0
    for tap_count, max_length in configurations:
        alphabet_size = 1 << tap_count
        masks = range(1, 1 << tap_count)
        for length in range(max_length + 1):
            universe = list(words(alphabet_size, length))
            for left in universe:
                for right in universe:
                    word_pairs += 1
                    projected = {mask: (project(left, mask), project(right, mask)) for mask in masks}
                    lcs_by_mask = {mask: lcs_grid(*pair) for mask, pair in projected.items()}
                    for mask, pair in projected.items():
                        projected_checks += 1
                        for budget in range(length + 1):
                            explicit = collides_by_enumeration(pair[0], pair[1], budget)
                            theorem = lcs_by_mask[mask] >= length - budget
                            theorem_checks += 1
                            if explicit != theorem:
                                raise AssertionError({
                                    "tap_count": tap_count, "length": length,
                                    "left": left, "right": right, "mask": mask,
                                    "budget": budget, "explicit": explicit,
                                    "lcs": lcs_by_mask[mask],
                                })
                    for small in masks:
                        for large in masks:
                            if small & large == small:
                                monotonicity_checks += 1
                                if lcs_by_mask[large] > lcs_by_mask[small]:
                                    raise AssertionError({
                                        "property": "projection monotonicity",
                                        "left": left, "right": right,
                                        "small": small, "large": large,
                                    })
    return {
        "word_pairs": word_pairs,
        "projected_pairs": projected_checks,
        "collision_equivalences": theorem_checks,
        "projection_monotonicity_relations": monotonicity_checks,
    }


def separates_all(traces: Sequence[Word], mask: int, budget: int) -> bool:
    for i in range(len(traces)):
        for j in range(i + 1, len(traces)):
            a = project(traces[i], mask)
            b = project(traces[j], mask)
            if collides_by_enumeration(a, b, budget):
                return False
    return True


def check_exact_selection() -> dict[str, int]:
    tap_count = 2
    length = 2
    universe = list(words(1 << tap_count, length))
    masks = list(range(1, 1 << tap_count))
    instances = feasible = infeasible = optimality_checks = 0
    histogram: dict[int, int] = {}
    for traces in itertools.product(universe, repeat=3):
        instances += 1
        feasible_masks = [mask for mask in masks if separates_all(traces, mask, 0)]
        if not feasible_masks:
            infeasible += 1
            continue
        feasible += 1
        optimum = min(mask.bit_count() for mask in feasible_masks)
        histogram[optimum] = histogram.get(optimum, 0) + 1
        chosen = min(feasible_masks, key=lambda mask: (mask.bit_count(), mask))
        if chosen.bit_count() != optimum:
            raise AssertionError("unit-cost exhaustive selector returned a non-optimum mask")
        for mask in masks:
            if mask.bit_count() < optimum:
                optimality_checks += 1
                if separates_all(traces, mask, 0):
                    raise AssertionError("a lower-cost separating mask contradicts the optimum")
    return {
        "instances": instances,
        "feasible": feasible,
        "infeasible": infeasible,
        "strictly_lower_cost_masks_rejected": optimality_checks,
        "optimum_one_tap": histogram.get(1, 0),
        "optimum_two_taps": histogram.get(2, 0),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = {
        "schema": "coverage-certified-exhaustive-small-v1",
        "status": "passed",
        "independence": "No import from src/trace_engine.py or src/check_certificate.py.",
        "collision_and_projection": check_collision_theorem(),
        "exact_selection": check_exact_selection(),
    }
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()

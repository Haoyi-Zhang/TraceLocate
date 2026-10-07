"""Owned portable scalar/oracle regressions; no RTL, timing or external input."""
from functools import lru_cache
from itertools import combinations, product
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import trace_engine as producer
from check_certificate import validate


@lru_cache(maxsize=None)
def subsequences(word, mask):
    return frozenset(tuple(word[i] & mask for i in inds)
                     for size in range(len(word) + 1)
                     for inds in combinations(range(len(word)), size))


def definition_length(x, y, mask):
    return max(map(len, subsequences(tuple(x), mask) & subsequences(tuple(y), mask)))


def own_model():
    words = ((0, 1, 2, 0), (2, 1, 0, 2), (0, 0, 2, 1))
    variants = {str(i): {'initial': [0, 0, 1], 'table': [
        [{'next': (q + 1) % len(w), 'row': v}] for q, v in enumerate(w)]}
        for i, w in enumerate(words)}
    return {'name': 'owned-row-loss', 'taps': [{'name': 'a', 'cost': 2}, {'name': 'b', 'cost': 1}],
            'variants': variants, 'classes': [{'name': str(i), 'variants': [str(i)]} for i in range(3)],
            'contexts': [{'name': 'own-fixed', 'inputs': [0] * 5}]}


class MinimumLossRowsTests(unittest.TestCase):
    def test_lengths_against_subsequence_definition(self):
        words = [w for size in range(4) for w in product(range(4), repeat=size)]
        count = 0
        for x, y, mask in product(words, words, range(4)):
            self.assertEqual(producer._lcs_length_rows(x, y, mask), definition_length(x, y, mask))
            count += 1
        self.assertEqual(count, 28900)

    def test_first_maximum_and_one_witness_grid(self):
        # Increasing lengths followed by a tie: strict first-maximum ordering.
        ps = [((0, 0, i, 1, 0), (0, 1, 2), y) for i, y in enumerate(
            ((3, 3, 3), (0, 3, 3), (0, 1, 3), (0, 1, 3)))]
        for mask in range(4):
            expected_lengths = [definition_length(x, y, mask) for _, x, y in ps]
            winner = expected_lengths.index(max(expected_lengths))
            with patch.object(producer, 'grid', wraps=producer.grid) as full_grid:
                margin = producer.minimum_loss(ps, mask)
                self.assertEqual(full_grid.call_count, 1)
            self.assertEqual(margin['pair'], list(ps[winner][0]))
            self.assertEqual(margin['loss'], 3 - max(expected_lengths))
            self.assertEqual(margin['alignment'], producer.alignment(ps[winner][1], ps[winner][2], mask))
            if not margin['loss']:
                self.assertEqual(margin['below'], [])
            else:
                for _, x, y in ps:
                    self.assertLess(definition_length(x, y, mask), 3 - margin['loss'] + 1)

    def test_complete_owned_packets_offsets_and_aliases(self):
        model = own_model()
        feasible = infeasible = 0
        for h, d, offsets in product(range(1, 5), range(5), ([0], [0, 1])):
            if d > h:
                continue
            spec = {'h': h, 'd': d, 'offsets': offsets, 'contexts': [0]}
            cert, stats = producer.synthesize(model, spec)
            self.assertEqual(validate(model, spec, cert)['status'], cert['status'])
            ps = producer.pairs(producer.languages(model, spec))
            self.assertEqual(stats['pairs'], len(ps))
            self.assertEqual(cert['full_margin']['loss'], h - max(definition_length(x, y, 3) for _, x, y in ps))
            good = [mask for mask in range(4) if all(definition_length(x, y, mask) < h - d for _, x, y in ps)]
            expected = min(good, key=lambda s: (producer.cost(s, [2, 1]), s.bit_count(), s)) if good else None
            self.assertEqual(cert['mask'], expected)
            feasible += cert['status'] == 'feasible'
            infeasible += cert['status'] == 'infeasible'
        self.assertGreater(feasible, 0)
        self.assertGreater(infeasible, 0)


if __name__ == '__main__':
    unittest.main()

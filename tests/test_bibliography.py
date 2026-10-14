"""Bibliographic records exclude presentation-only BibTeX directives."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from verify_bibliography import parse_bib


class BibliographyDirectiveTest(unittest.TestCase):
    def parse(self, text):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "references.bib"
            path.write_text(text, encoding="utf-8")
            return parse_bib(path)

    def test_ieee_style_control_is_not_an_uncited_reference(self):
        entries = self.parse(
            "@IEEEtranBSTCTL{authorDisplay, CTLdash_repeated_names={no}}\n"
            "@article{work, author={A. Writer}, title={A result}, year={2001}}\n"
        )
        self.assertEqual([entry["key"] for entry in entries], ["work"])
        self.assertEqual(entries[0]["author"], "A. Writer")

    def test_control_in_middle_does_not_hide_later_missing_title(self):
        entries = self.parse(
            "@article{first, title={First result}}\n"
            "@ieeetranbstctl{style, CTLdash_repeated_names={no}}\n"
            "@article{incomplete, author={A. Writer}}\n"
        )
        self.assertEqual([entry["key"] for entry in entries], ["first", "incomplete"])
        self.assertNotIn("title", entries[1])


if __name__ == "__main__":
    unittest.main()

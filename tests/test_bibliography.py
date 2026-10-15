"""Bibliographic records exclude presentation-only BibTeX directives."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from verify_bibliography import parse_bib
from reviewer_gate import bib_keys, run, valid_package_members


class BibliographyDirectiveTest(unittest.TestCase):
    def test_gate_accepts_the_delivery_layout_without_unrelated_files(self):
        self.assertTrue(valid_package_members({'paper', 'artifact'}))
        self.assertTrue(valid_package_members({'paper', 'artifact', 'README.md'}))
        self.assertFalse(valid_package_members({'artifact'}))
        self.assertFalse(valid_package_members({'paper', 'artifact', 'unexpected.txt'}))

    def test_tool_output_is_decoded_as_utf8(self):
        output = run([sys.executable, '-c',
                      "import sys; sys.stdout.buffer.write(bytes([0xe9, 0x9b, 0xaa]))"], ROOT)
        self.assertEqual(output, '\u96ea')

    def test_reviewer_gate_excludes_style_directives(self):
        text = ("  @IEEEtranBSTCTL{authorDisplay, CTLdash_repeated_names={no}}\n"
                "@article{work, author={A. Writer}, title={A result}, year={2001}}\n")
        self.assertEqual(bib_keys(text), ["work"])

    def test_reviewer_gate_keeps_incomplete_real_entries(self):
        text = ("@article{first, title={First result}}\n"
                "@ieeetranbstctl{style, CTLdash_repeated_names={no}}\n"
                "@article{incomplete, author={A. Writer}}\n")
        self.assertEqual(bib_keys(text), ["first", "incomplete"])

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

"""Public entry and child commands leave source trees free of bytecode caches."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import _reproduce_core as core


class EntrypointTests(unittest.TestCase):
    def test_help_does_not_write_import_caches(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'src').mkdir()
            for name in ('reproduce.py', '_reproduce_core.py', 'src/output_safety.py'):
                shutil.copy2(ROOT / name, root / name)
            env = {k: v for k, v in os.environ.items()
                   if k not in ('PYTHONDONTWRITEBYTECODE', 'PYTHONPYCACHEPREFIX')}
            result = subprocess.run([sys.executable, str(root / 'reproduce.py'), '--help'],
                                    cwd=root, env=env, capture_output=True, text=True,
                                    timeout=20, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('--retained-only', result.stdout)
            self.assertIn('--iverilog', result.stdout)
            self.assertEqual(list(root.rglob('__pycache__')), [])

    def test_child_import_does_not_write_a_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'owned_helper.py').write_text('VALUE = 17\n', encoding='utf-8')
            result = core.run([sys.executable, '-c',
                               'import owned_helper; print(owned_helper.VALUE)'], cwd=root)
            self.assertEqual(result.strip(), '17')
            self.assertEqual(list(root.rglob('__pycache__')), [])


if __name__ == '__main__':
    unittest.main()

import ast
import unittest
from pathlib import Path

class ElementNameTests(unittest.TestCase):
    def test_logged_nail_name_and_reserved_characters(self):
        source = Path(__file__).resolve().parents[1] / 'lib' / 'rt_revit.py'
        tree = ast.parse(source.read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name=='safe_element_name')
        scope = dict(text_type=str)
        exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),scope)
        safe = scope['safe_element_name']
        logged = 'RT 0.148 x 1.5 in hand connector nail | Unspecified - review'
        self.assertEqual(safe(logged), logged.replace('|','-'))
        self.assertEqual(safe('RT normal name'), 'RT normal name')
        for c in chr(92)+':{}[]|;<>?`~'+chr(10):
            self.assertNotIn(c, safe('RT '+c+' nail'))
        self.assertTrue(safe(''))

    def test_direct_shape_name_uses_sanitizer(self):
        source = Path(__file__).resolve().parents[1] / 'lib' / 'rt_revit.py'
        tree = ast.parse(source.read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name=='shape')
        assignments = [n for n in ast.walk(node) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Attribute) and t.attr=='Name' for t in n.targets)]
        self.assertEqual(len(assignments),1)
        self.assertEqual(assignments[0].value.func.id,'safe_element_name')

import unittest, pathlib, tomllib

class LoaderMetadata(unittest.TestCase):
    def test_sdk_default_parser(self):
        parse = lambda v: tuple(int(x) for x in v.split('.'))
        with self.assertRaises(ValueError):
            parse('0.7.0.dev1')
        path = pathlib.Path(__file__).parent / 'bl4_custom_foundation' / 'pyproject.toml'
        version = tomllib.loads(path.read_text())['project']['version']
        self.assertEqual(parse(version), (0, 7, 47))

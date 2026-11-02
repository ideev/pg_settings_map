"""Offline catalogue checks: python3 -m unittest discover -s tests -p 'test_qhb_documentation.py'."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import apply_qhb_documentation_links as qhb


class QhbDocumentationTests(unittest.TestCase):
    def test_catalogue_preserves_other_properties_and_is_repeatable(self):
        settings = json.loads((qhb.ROOT / 'pg_settings.json').read_text())
        catalogue = json.loads(qhb.CATALOGUE.read_text())
        expected = copy.deepcopy(settings)
        for node in qhb.parameters(settings).values():
            node.pop('qhb_documentation_link', None)
        qhb.apply(settings, catalogue)
        self.assertEqual(settings, expected)
        qhb.apply(settings, catalogue)
        self.assertEqual(settings, expected)
        self.assertEqual(len(catalogue['links']), 420)
        self.assertEqual(len(qhb.parameters(settings)), 436)
        self.assertEqual(set(catalogue['parameters_without_description']),
                         set(qhb.parameters(settings)) - set(catalogue['links']))

    def test_actual_heading_anchors_case_and_recovery_target(self):
        names = ['work_mem', 'DateStyle', 'recovery_target', 'qhb_cache_size']
        settings = {'type': 'root', 'name': 'PostgreSQL', 'children': [
            {'type': 'parameter', 'name': name} for name in names]}
        pages = {'Configuration/runtime-config/runtime-config-test.html': '''
            <h4><a id="actual-anchor">work_mem (integer)</a></h4>
            <h4><a id="datestyle-string">DateStyle (string)</a></h4>
            <h4><a id="recovery_target--immediate">recovery_target = 'immediate'</a></h4>
            <h4><a id="qhb_cache_size-integer">qhb_cache_size (integer)</a></h4>
            <h4><a id="another-anchor">work_mem (integer)</a></h4>
            <p>undocumented_parameter</p>'''}
        with patch.dict(qhb.SUPPLEMENTS, {}, clear=True):
            result = qhb.collect(settings, pages)
        self.assertEqual(set(result['links']), set(names))
        self.assertEqual(urlsplit(result['links']['work_mem']['url']).fragment, 'actual-anchor')
        self.assertEqual(len(result['duplicate_definitions']['work_mem']), 2)

    def test_invalid_catalogue_does_not_mutate_settings(self):
        settings = json.loads((qhb.ROOT / 'pg_settings.json').read_text())
        expected = copy.deepcopy(settings)
        catalogue = json.loads(qhb.CATALOGUE.read_text())
        for url in ['http://repo.quantom.info/x.html#a',
                    qhb.BASE + '../outside.html#a',
                    qhb.BASE + '%2e%2e/outside.html#a',
                    'https://repo.quantom.info.evil.test/x.html#a',
                    qhb.BASE + 'Configuration/runtime-config.html']:
            with self.subTest(url=url):
                bad = copy.deepcopy(catalogue)
                next(iter(bad['links'].values()))['url'] = url
                with self.assertRaises(ValueError):
                    qhb.apply(settings, bad)
                self.assertEqual(settings, expected)

    def test_supplement_requires_parameter_inside_the_target_section(self):
        settings = {'type': 'root', 'name': 'PostgreSQL', 'children': [{'type': 'parameter', 'name': 'custom_guc'}]}
        pages = {'Internal/test.html': '<h2><a id="target">Config</a></h2><p>other</p><h2><a id="elsewhere">Other</a></h2><p>custom_guc</p>'}
        with patch.dict(qhb.SUPPLEMENTS, {'Internal/test.html#target': ['custom_guc']}, clear=True):
            with self.assertRaises(ValueError):
                qhb.collect(settings, pages)


if __name__ == '__main__':
    unittest.main()

import contextlib
import io
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from xml.etree import ElementTree
from zipfile import ZipFile

import iciba

ROOT = Path(__file__).resolve().parents[1]


class QueryTests(unittest.TestCase):
    def output(self, function, *args):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
            function(*args)
        return ElementTree.fromstring(stdout.getvalue())

    def lookup(self, base):
        with patch.object(iciba, '_get_json', return_value={'message': {'baesInfo': base}}):
            return self.output(iciba.get_phonetic_symbols_new, 'hello', {})

    def test_english_definitions(self):
        result = self.lookup({'symbols': [{
            'ph_en': 'həˈləʊ', 'ph_am': 'həˈloʊ',
            'parts': [{'part': 'int.', 'means': ['你好', '喂']},
                      {'part': 'n.', 'means': ['问候声']}],
        }]})
        self.assertEqual(len(result), 2)
        self.assertIn('英:[həˈləʊ]', result[0].findtext('title'))
        self.assertEqual(result[0].findtext('subtitle'), 'int. 你好; 喂')

    def test_chinese_and_missing_phonetics(self):
        for extra, title in [({'word_symbol': 'nǐ hǎo'}, 'hello 拼音:[nǐ hǎo]'),
                             ({}, 'hello')]:
            with self.subTest(extra=extra):
                result = self.lookup({'symbols': [
                    dict(extra, parts=[{'part': '', 'means': ['hello', 'hi']}])
                ]})
                self.assertEqual(result[0].findtext('title'), title)

    def test_translation_and_unknown_word(self):
        translated = self.lookup({'translate_result': '你好'})
        self.assertEqual(translated[0].findtext('title'), 'hello => 你好')
        for base in [{}, {'symbols': None}, {'translate_result': 'hello'}]:
            with self.subTest(base=base):
                result = self.lookup(base)
                self.assertIn('未找到', result[0].findtext('title'))
                self.assertEqual(result[0].get('arg'), iciba._page_url('hello'))

    def test_lookup_errors_always_return_xml_and_web_fallback(self):
        errors = [TimeoutError('timeout'), URLError('offline'),
                  HTTPError('https://example.com', 503, 'Unavailable', {}, None),
                  ValueError('invalid JSON')]
        for error in errors:
            if isinstance(error, HTTPError):
                self.addCleanup(error.close)
            with self.subTest(error=error):
                with patch.object(iciba, '_get_json', side_effect=error):
                    result = self.output(iciba.get_phonetic_symbols_new, '你好 & C++', {})
                self.assertEqual(result[0].findtext('title'), '查询失败')
                url = result[0].get('arg')
                self.assertEqual(parse_qs(urlsplit(url).query)['w'], ['你好 & C++'])

    def test_invalid_response_or_definition_does_not_crash(self):
        responses = [{}, {'message': None}, {'message': {'baesInfo': None}},
                     {'message': {'baesInfo': {'symbols': [{'parts': [
                         {'means': ['valid']}, {'means': [42]}
                     ]}]}}}]
        for response in responses:
            with self.subTest(response=response):
                with patch.object(iciba, '_get_json', return_value=response):
                    result = self.output(iciba.get_phonetic_symbols_new, 'hello', {})
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0].findtext('title'), '查询失败')

    def test_suggestions_keep_autocomplete_and_selected_word(self):
        response = {'message': [
            {'key': 'hello', 'means': [{'part': 'int.', 'means': ['你好']}]},
            {'key': 'hello world', 'means': None},
        ]}
        with patch.object(iciba, '_get_json', return_value=response):
            result = self.output(iciba.get_suggest, 'hel', {})
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].get('autocomplete'), '> hello')
        self.assertEqual(result[0].get('valid'), 'no')
        self.assertEqual(result[0].get('arg'), iciba._page_url('hello'))
        self.assertEqual(result[1].get('autocomplete'), '> hello world')

    def test_empty_or_unavailable_suggestions_allow_direct_lookup(self):
        for response in [{'message': []}, {'message': 'bad response'}, {}]:
            with self.subTest(response=response):
                with patch.object(iciba, '_get_json', return_value=response):
                    result = self.output(iciba.get_suggest, 'hello', {})
                self.assertEqual(result[0].get('autocomplete'), '> hello')
                self.assertEqual(result[0].get('valid'), 'no')
        with patch.object(iciba, '_get_json', side_effect=TimeoutError):
            result = self.output(iciba.get_suggest, '你好', {})
        self.assertEqual(result[0].get('autocomplete'), '> 你好')

    def test_empty_input_never_calls_network(self):
        with patch.object(iciba, '_get_json') as request:
            for args in [[], [''], ['  '], [' >  ']]:
                result = self.output(iciba.main, args)
                self.assertEqual(result[0].get('valid'), 'no')
            request.assert_not_called()

    def test_only_leading_marker_selects_lookup(self):
        with patch.object(iciba, 'get_suggest') as suggest:
            iciba.main([' C > C++ '])
            self.assertEqual(suggest.call_args.args[0], 'C > C++')
        with patch.object(iciba, 'get_phonetic_symbols_new') as lookup:
            iciba.main([' > C > C++ '])
            self.assertEqual(lookup.call_args.args[0], 'C > C++')

    def test_transport_encodes_query_and_sets_timeout(self):
        word = "你好 & C++ / #'?"
        with patch.object(iciba, 'urlopen', return_value=io.BytesIO(b'{"message": []}')) as open_url:
            self.assertEqual(iciba._get_json('https://example.com/api',
                                            {'word': word}, {'User-Agent': 'test'}),
                             {'message': []})
        request = open_url.call_args.args[0]
        self.assertEqual(parse_qs(urlsplit(request.full_url).query)['word'], [word])
        self.assertEqual(request.get_header('User-agent'), 'test')
        self.assertEqual(open_url.call_args.kwargs['timeout'], 10)


class WorkflowTests(unittest.TestCase):
    def test_launcher_preserves_query_and_interpreter_path_with_spaces(self):
        config = plistlib.loads((ROOT / 'info.plist').read_bytes())['objects'][0]['config']
        self.assertEqual(config['scriptargtype'], 1)
        self.assertNotIn('{query}', config['script'])
        with tempfile.TemporaryDirectory(prefix='iciba test ') as directory:
            directory = Path(directory)
            python = directory / 'python with spaces'
            python.symlink_to(sys.executable)
            (directory / 'iciba.py').write_text(
                'import json,sys; print(json.dumps(sys.argv[1:]))')
            query = """你好 ' " \\ $HOME $(echo wrong) `echo wrong` & >"""
            env = dict(os.environ, path_to_python3=str(python))
            result = subprocess.run(
                ['/bin/bash', '-c', config['script'], 'workflow', query],
                cwd=directory, env=env, capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout), [query])

    def test_runs_without_site_packages(self):
        result = subprocess.run([sys.executable, '-S', str(ROOT / 'iciba.py'), '>'],
                                cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertEqual(ElementTree.fromstring(result.stdout).tag, 'items')

    def test_bundle_matches_sources_and_runs_without_dependencies(self):
        expected = {'iciba.py', 'info.plist', 'icon.png'}
        expected.update(path.relative_to(ROOT).as_posix()
                        for path in (ROOT / 'alfred').glob('*.py'))
        with ZipFile(ROOT / 'bundle/iciba.alfredworkflow') as archive:
            self.assertEqual(set(archive.namelist()), expected)
            for name in expected:
                self.assertEqual(archive.read(name), (ROOT / name).read_bytes(), name)
            with tempfile.TemporaryDirectory() as directory:
                archive.extractall(directory)
                result = subprocess.run([sys.executable, '-S', 'iciba.py', '>'],
                                        cwd=directory, capture_output=True,
                                        text=True, check=True)
                self.assertEqual(ElementTree.fromstring(result.stdout).tag, 'items')


if __name__ == '__main__':
    unittest.main()

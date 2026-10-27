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
    def setUp(self):
        local = patch.object(iciba, '_local_translate', return_value=None)
        self.local = local.start()
        self.addCleanup(local.stop)

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



    def test_valid_dictionary_and_machine_results_skip_local_translation(self):
        self.lookup({'symbols': [{'parts': [{'means': ['你好']}]}]})
        self.lookup({'translate_result': '你好'})
        self.local.assert_not_called()

    def test_missing_or_blank_results_use_local_translation(self):
        self.local.return_value = {'status': 'translated', 'translation': '你好世界'}
        bases = [{}, {'symbols': [{'parts': [{'means': [' ', '']}]}]},
                 {'translate_result': ' HELLO '}, {'translate_result': '  '}]
        for base in bases:
            with self.subTest(base=base):
                self.local.reset_mock()
                result = self.lookup(base)
                self.local.assert_called_once_with('hello')
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0].findtext('subtitle'), 'Apple 本地翻译')
                self.assertIn('你好世界', result[0].findtext('title'))

    def test_network_failure_uses_local_translation(self):
        self.local.return_value = {'status': 'translated', 'translation': '你好'}
        with patch.object(iciba, '_get_json', side_effect=TimeoutError):
            result = self.output(iciba.get_phonetic_symbols_new, 'hello', {})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].findtext('subtitle'), 'Apple 本地翻译')

    def test_local_translation_is_not_used_during_suggestions(self):
        with patch.object(iciba, '_get_json', side_effect=TimeoutError):
            result = self.output(iciba.get_suggest, 'hello', {})
        self.local.assert_not_called()
        self.assertEqual(result[0].get('autocomplete'), '> hello')

    def test_unusable_local_results_preserve_web_lookup(self):
        for response in [
            {'status': 'translated', 'translation': ' HELLO '},
            {'status': 'translated', 'translation': ''},
            {'status': 'not_installed', 'message': '请下载语言'},
            {'status': 'error'},
        ]:
            with self.subTest(response=response):
                self.local.return_value = response
                result = self.lookup({})
                self.assertEqual(result[0].get('valid'), 'no')
                self.assertEqual(result[-1].get('arg'), iciba._page_url('hello'))


class LocalTranslationTests(unittest.TestCase):
    def setUp(self):
        self.enter = contextlib.ExitStack()
        self.addCleanup(self.enter.close)
        self.enter.enter_context(patch.dict(os.environ, {
            'apple_translation': '1', 'translation_source': '', 'translation_target': '',
        }))
        self.enter.enter_context(patch.object(sys, 'platform', 'darwin'))
        self.enter.enter_context(patch.object(iciba.platform, 'mac_ver', return_value=('26.0', (), '')))
        self.run = self.enter.enter_context(patch.object(iciba.subprocess, 'run'))
        self.run.return_value = subprocess.CompletedProcess([], 0,
            '{"status": "translated", "translation": "你好"}', '')

    def test_text_is_sent_as_json_on_stdin_without_a_shell(self):
        word = "hello ' \" & $(echo wrong)"
        result = iciba._local_translate(word)
        self.assertEqual(result['translation'], '你好')
        self.assertEqual(len(self.run.call_args.args[0]), 1)
        self.assertEqual(json.loads(self.run.call_args.kwargs['input']), {'text': word})
        self.assertEqual(self.run.call_args.kwargs['timeout'], 12)
        self.assertNotIn('shell', self.run.call_args.kwargs)

    def test_configured_languages_are_forwarded(self):
        with patch.dict(os.environ, {'translation_source': 'en', 'translation_target': 'ja'}):
            iciba._local_translate('hello')
        request = json.loads(self.run.call_args.kwargs['input'])
        self.assertEqual(request, {'text': 'hello', 'source': 'en', 'target': 'ja'})

    def test_disabled_or_older_platform_never_launches_helper(self):
        with patch.dict(os.environ, {'apple_translation': '0'}):
            self.assertIsNone(iciba._local_translate('hello'))
        with patch.object(iciba.platform, 'mac_ver', return_value=('15.0', (), '')):
            self.assertEqual(iciba._local_translate('hello')['status'], 'unavailable')
        with patch.object(sys, 'platform', 'linux'):
            self.assertEqual(iciba._local_translate('hello')['status'], 'unavailable')
        self.run.assert_not_called()

    def test_timeout_missing_helper_and_invalid_json_are_safe(self):
        for error in [FileNotFoundError(), TimeoutError(),
                      subprocess.TimeoutExpired('apple-translate', 12),
                      subprocess.CalledProcessError(1, ['apple-translate'])]:
            with self.subTest(error=error):
                self.run.side_effect = error
                self.assertIn(iciba._local_translate('hello')['status'], ('error', 'unavailable'))
        self.run.side_effect = None
        for output in ['not json', 'null', '[]']:
            self.run.return_value.stdout = output
            self.assertEqual(iciba._local_translate('hello')['status'], 'error')


@unittest.skipUnless(sys.platform == 'darwin', 'Apple Translation requires macOS')
class NativeTranslationTests(unittest.TestCase):
    def run_helper(self, request):
        helper = ROOT / 'bin' / 'apple-translate'
        result = subprocess.run([str(helper)], input=json.dumps(request),
                                capture_output=True, text=True, check=True, timeout=20)
        return json.loads(result.stdout)

    def test_installed_language_check(self):
        if int(iciba.platform.mac_ver()[0].split('.')[0]) < 26:
            self.skipTest('Native helper requires macOS 26+')
        response = self.run_helper({'text': 'hello', 'source': 'en',
                                    'target': 'zh-Hans', 'checkOnly': True})
        self.assertIn(response['status'], ('installed', 'not_installed'))
        self.assertEqual(response['source'], 'en')
        self.assertEqual(response['target'], 'zh-Hans')

    def test_real_translation_when_languages_are_installed(self):
        if int(iciba.platform.mac_ver()[0].split('.')[0]) < 26:
            self.skipTest('Native helper requires macOS 26+')
        for text, source, target in [('Good morning, how are you?', 'en', 'zh-Hans'),
                                     ('早上好，你今天怎么样？', 'zh-Hans', 'en')]:
            request = {'text': text, 'source': source, 'target': target, 'checkOnly': True}
            if self.run_helper(request)['status'] != 'installed':
                self.skipTest('Download English and Chinese translation packs to run this test')
            request['checkOnly'] = False
            response = self.run_helper(request)
            self.assertEqual(response['status'], 'translated', response)
            self.assertTrue(iciba._usable_translation(response['translation'], text))


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
        expected = {'iciba.py', 'info.plist', 'icon.png', 'bin/apple-translate'}
        expected.update(path.relative_to(ROOT).as_posix()
                        for path in (ROOT / 'alfred').glob('*.py'))
        with ZipFile(ROOT / 'bundle/iciba.alfredworkflow') as archive:
            self.assertEqual(set(archive.namelist()), expected)
            self.assertTrue(archive.getinfo('bin/apple-translate').external_attr >> 16 & 0o111)
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

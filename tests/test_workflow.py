import contextlib
import io
import json
import os
from pathlib import Path
import plistlib
import shlex
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
                  HTTPError('https://example.com', 503, 'Unavailable', {}, io.BytesIO(b'Unavailable')),
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

    def test_empty_or_unavailable_suggestions_continue_to_lookup(self):
        ordinary = {'message': {'baesInfo': {'translate_result': '你好'}}}
        for response in [{'message': []}, {'message': 'bad response'}, {}, TimeoutError()]:
            with self.subTest(response=response):
                with patch.object(iciba, '_get_json', side_effect=[response, ordinary]):
                    result = self.output(iciba.get_suggest, 'hello', {})
                self.assertEqual(result[0].findtext('title'), 'hello => 你好')
        self.local.assert_not_called()

    def test_phrases_skip_suggestion_service(self):
        with patch.object(iciba, 'get_phonetic_symbols_new') as lookup:
            with patch.object(iciba, '_get_json') as request:
                iciba.get_suggest('Good morning, how are you?', {})
                request.assert_not_called()
            lookup.assert_called_once_with('Good morning, how are you?', {})

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
        self.assertEqual(open_url.call_args.kwargs['timeout'], 2)



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

    def test_unavailable_suggestions_can_reach_local_translation(self):
        self.local.return_value = {'status': 'translated', 'translation': '你好'}
        with patch.object(iciba, '_get_json', side_effect=[
                TimeoutError(), {'message': {'baesInfo': {}}}]):
            result = self.output(iciba.get_suggest, 'hello', {})
        self.local.assert_called_once_with('hello')
        self.assertEqual(result[0].findtext('subtitle'), 'Apple 本地翻译')

    def test_valid_suggestions_skip_local_translation(self):
        with patch.object(iciba, '_get_json', return_value={
                'message': [{'key': 'hello', 'means': [{'means': ['你好']}]}]}):
            self.output(iciba.get_suggest, 'hello', {})
        self.local.assert_not_called()

    def test_unchanged_or_empty_local_translation_is_not_an_availability_error(self):
        for translation in [' HELLO ', '', '  ']:
            with self.subTest(translation=translation):
                self.local.return_value = {'status': 'translated', 'translation': translation}
                result = self.lookup({})
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0].findtext('title'), '未找到 "hello" 的翻译')
                self.assertEqual(result[0].get('arg'), iciba._page_url('hello'))
                self.assertNotIn('不可用', ElementTree.tostring(result, encoding='unicode'))
                self.assertNotIn('语言包', ElementTree.tostring(result, encoding='unicode'))

    def test_no_translation_after_network_error_is_still_a_completed_attempt(self):
        self.local.return_value = {'status': 'translated', 'translation': 'hello'}
        with patch.object(iciba, '_get_json', side_effect=TimeoutError()):
            result = self.output(iciba.get_phonetic_symbols_new, 'hello', {})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].findtext('title'), '未找到 "hello" 的翻译')

    def test_local_failures_explain_the_specific_condition_and_keep_web_lookup(self):
        cases = [
            ({'status': 'not_installed', 'message': '请下载语言', 'source': 'en',
              'target': 'ja'}, '缺少本次翻译所需的语言包', 'en → ja'),
            ({'status': 'unsupported', 'message': '不支持的语言组合', 'source': 'nb',
              'target': 'zh-Hans'}, 'Apple 不支持此语言组合', 'nb → zh-Hans'),
            ({'status': 'error', 'message': 'Apple 本地翻译暂不可用'},
             'Apple 未能完成本次翻译', '本次翻译失败'),
        ]
        for response, title, subtitle in cases:
            with self.subTest(response=response):
                self.local.return_value = response
                result = self.lookup({})
                self.assertEqual(result[0].findtext('title'), title)
                self.assertIn(subtitle, result[0].findtext('subtitle'))
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
        self.spawn = self.enter.enter_context(patch.object(iciba.subprocess, 'Popen'))
        self.process = self.spawn.return_value
        self.process.returncode = 0
        self.process.communicate.return_value = (
            '{"status": "translated", "translation": "你好"}', '')

    def test_text_is_sent_as_json_on_stdin_without_a_shell(self):
        word = "hello ' & $(echo wrong)"
        result = iciba._local_translate(word)
        self.assertEqual(result['translation'], '你好')
        self.assertEqual(len(self.spawn.call_args.args[0]), 1)
        self.assertEqual(json.loads(self.process.communicate.call_args.args[0]), {'text': word})
        self.assertEqual(self.process.communicate.call_args.kwargs['timeout'], 12)
        self.assertNotIn('shell', self.spawn.call_args.kwargs)

    def test_configured_languages_are_forwarded(self):
        with patch.dict(os.environ, {'translation_source': 'en', 'translation_target': 'ja'}):
            iciba._local_translate('hello')
        request = json.loads(self.process.communicate.call_args.args[0])
        self.assertEqual(request, {'text': 'hello', 'source': 'en', 'target': 'ja'})

    def test_unusable_language_guess_for_single_word_retries_english(self):
        for status in ['not_installed', 'unsupported']:
            with self.subTest(status=status):
                self.process.communicate.reset_mock()
                self.process.communicate.side_effect = [
                    (json.dumps({'status': status, 'source': 'pt', 'target': 'zh-Hans'}), ''),
                    (json.dumps({'status': 'translated', 'source': 'en',
                                 'translation': 'OpenAI'}), ''),
                ]
                result = iciba._local_translate('OpenAI')
                self.assertEqual(result['status'], 'translated')
                requests = [json.loads(call.args[0])
                            for call in self.process.communicate.call_args_list]
                self.assertNotIn('source', requests[0])
                self.assertEqual(requests[1], {'text': 'OpenAI', 'source': 'en'})

    def test_explicit_source_phrase_and_existing_english_guess_are_not_retried(self):
        cases = [
            ('OpenAI', 'pt', 'pt', ''),
            ('bonjour tout le monde', '', 'fr', ''),
            ('OpenAI', '', 'en', ''),
            ('bonjour', '', 'fr', 'en-US'),
        ]
        for text, configured, detected, target in cases:
            with self.subTest(text=text, configured=configured, detected=detected):
                self.process.communicate.reset_mock()
                self.process.communicate.return_value = (
                    json.dumps({'status': 'not_installed', 'source': detected}), '')
                with patch.dict(os.environ, {'translation_source': configured,
                                             'translation_target': target}):
                    result = iciba._local_translate(text)
                self.assertEqual(result['status'], 'not_installed')
                self.assertEqual(self.process.communicate.call_count, 1)

    def test_successful_non_english_detection_is_preserved(self):
        self.process.communicate.return_value = (
            json.dumps({'status': 'translated', 'source': 'fr', 'translation': '你好'}), '')
        result = iciba._local_translate('bonjour')
        self.assertEqual(result['source'], 'fr')
        self.assertEqual(self.process.communicate.call_count, 1)

    def test_disabled_or_older_platform_never_launches_helper(self):
        with patch.dict(os.environ, {'apple_translation': '0'}):
            self.assertIsNone(iciba._local_translate('hello'))
        with patch.object(iciba.platform, 'mac_ver', return_value=('15.0', (), '')):
            self.assertEqual(iciba._local_translate('hello')['status'], 'unavailable')
        with patch.object(sys, 'platform', 'linux'):
            self.assertEqual(iciba._local_translate('hello')['status'], 'unavailable')
        self.spawn.assert_not_called()

    def test_missing_helper_failed_process_and_invalid_json_are_safe(self):
        self.spawn.side_effect = FileNotFoundError()
        self.assertEqual(iciba._local_translate('hello')['status'], 'unavailable')
        self.spawn.side_effect = None
        self.process.returncode = 1
        self.assertEqual(iciba._local_translate('hello')['status'], 'error')
        self.process.returncode = 0
        for output in ['not json', 'null', '[]']:
            self.process.communicate.return_value = (output, '')
            self.assertEqual(iciba._local_translate('hello')['status'], 'error')

    def test_timeout_and_cancel_stop_the_native_process(self):
        for error in [subprocess.TimeoutExpired('apple-translate', 12), SystemExit(0)]:
            with self.subTest(error=error):
                self.process.reset_mock()
                self.process.poll.return_value = None
                self.process.communicate.side_effect = [error, ('', '')]
                with self.assertRaises(type(error)):
                    iciba._run_translation_helper('apple-translate', {'text': 'old query'})
                self.process.kill.assert_called_once()
                self.assertEqual(self.process.communicate.call_count, 2)


class CancellationTests(unittest.TestCase):
    def test_terminating_query_reaps_its_translator_child(self):
        import signal
        import socket
        with socket.socket() as ready, tempfile.TemporaryDirectory() as directory:
            ready.bind(('127.0.0.1', 0))
            ready.listen(1)
            ready.settimeout(5)
            helper = Path(directory) / 'translator'
            helper_code = (
                'import os,socket; '
                'connection=socket.create_connection(("127.0.0.1", ' +
                str(ready.getsockname()[1]) + ')); '
                'connection.sendall(str(os.getpid()).encode()); '
                'connection.recv(1)')
            helper.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) +
                              ' -c ' + shlex.quote(helper_code) + '\n')
            helper.chmod(0o755)
            code = ('import iciba,signal,sys; '
                    'signal.signal(signal.SIGTERM,iciba._cancel_query); '
                    'iciba._run_translation_helper(sys.argv[1],{})')
            worker = subprocess.Popen([sys.executable, '-c', code, str(helper)], cwd=ROOT,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            child_pid = None
            try:
                with ready.accept()[0] as connection:
                    connection.settimeout(5)
                    child_pid = int(connection.recv(64))
                    worker.send_signal(signal.SIGTERM)
                    self.assertEqual(worker.wait(timeout=5), 0)
                    with self.assertRaises(ProcessLookupError):
                        os.kill(child_pid, 0)
            finally:
                if worker.poll() is None:
                    worker.kill()
                worker.communicate(timeout=5)
                if child_pid is not None:
                    try:
                        os.kill(child_pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass


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

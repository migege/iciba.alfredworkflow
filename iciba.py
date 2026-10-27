#!/usr/bin/env python3
# -*- coding:utf8 -*-

__author__ = 'lzw.whu@gmail.com'
__version__ = '20261027:12'

from alfred.feedback import Feedback

import hashlib
import json
import sys
import time
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

_TIMEOUT = 10
_SUGGEST_TIMEOUT = 3
ICIBA_PAGE = 'https://www.iciba.com/word?w={}'


def _page_url(word):
    return ICIBA_PAGE.format(quote(word, safe=''))


def _get_json(url, params, headers, timeout=_TIMEOUT):
    request = Request(url + '?' + urlencode(params), headers=headers)
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def _error_feedback(word, error, suggest=False):
    # Alfred's debugger reads stderr; errors must never corrupt XML on stdout.
    print('iciba: {} | word={}'.format(error, word), file=sys.stderr)
    fb = Feedback()
    if suggest:
        fb.addItem(title='查询 "{}"'.format(word),
                   subtitle='建议暂不可用，回车直接查词',
                   autocomplete='> {}'.format(word), valid=False)
    else:
        fb.addItem(title='查询失败',
                   subtitle='回车打开词霸网页查询',
                   arg=_page_url(word))
    return fb


def _add_mean_items(fb, word, symbol):
    """把一条 symbol 的释义拆成多个 Feedback item 追加进去。"""
    if 'ph_en' in symbol and 'ph_am' in symbol:
        title = '{word} 英:[{en}] 美:[{am}]'.format(
            word=word, en=symbol['ph_en'], am=symbol['ph_am'])
    elif 'word_symbol' in symbol:
        title = '{word} 拼音:[{word_symbol}]'.format(
            word=word, word_symbol=symbol['word_symbol'])
    else:
        title = word
    for mean in symbol.get('parts', []):
        subtitle = '; '.join(mean['means'])
        if mean.get('part'):
            subtitle = mean['part'] + ' ' + subtitle
        fb.addItem(title=title, subtitle=subtitle, arg=_page_url(word))


def get_phonetic_symbols_new(word, headers):
    word = word.strip()
    data = [
        ("client", "6"),
        ("key", "1000006"),
        ("timestamp", str(int(time.time() * 1000))),
        ("word", word),
    ]
    url = "https://dict.iciba.com/dictionary/word/query/web"

    # 签名规则:路径 + 各参数值 + 盐（先签名原始值，再 URL 编码）
    to_sign = '/dictionary/word/query/web'
    to_sign += ''.join(value for _, value in data)
    to_sign += "7ece94d9f9c202b0d2ec557dg4r9bc"
    data.append(("signature", hashlib.md5(to_sign.encode('utf8')).hexdigest()))

    fb = Feedback()
    try:
        res = _get_json(url, data, headers)
        base = res["message"]['baesInfo']
        for symbol in base.get('symbols') or []:
            _add_mean_items(fb, word, symbol)

        # 没有词典释义时，回退到接口给出的机器翻译结果。
        if fb.isEmpty():
            translate = base.get('translate_result') or ''
            if translate and translate != word:
                fb.addItem(
                    title='{word} => {trans}'.format(word=word, trans=translate),
                    subtitle=base.get('translate_msg') or '机器翻译结果',
                    arg=_page_url(word))
            else:
                fb.addItem(title='未找到 "{}"'.format(word),
                           subtitle='回车打开词霸网页查询',
                           arg=_page_url(word))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as ex:
        fb = _error_feedback(word, ex)
    fb.output()


def get_suggest(q, headers):
    q = q.strip()
    params = {
        'c': 'word',
        'm': 'getsuggest',
        'nums': '5',
        'client': '6',
        'uid': '0',
        'is_need_mean': '1',
        'word': q,
    }
    url = 'https://dict-mobile.iciba.com/interface/index.php'
    fb = Feedback()
    try:
        res = _get_json(url, params, headers, timeout=_SUGGEST_TIMEOUT)
        messages = res['message']
        if not isinstance(messages, list):
            raise ValueError('Invalid suggestion response')
        for msg in messages:
            word = msg['key']
            means = msg.get('means') or []
            if not means:
                fb.addItem(title=word,
                           autocomplete='> {}'.format(word), valid=False)
            for mean in means:
                subtitle = '; '.join(mean['means'])
                if mean.get('part'):
                    subtitle = mean['part'] + ' ' + subtitle
                fb.addItem(title=word, subtitle=subtitle,
                           arg=_page_url(word),
                           autocomplete='> {}'.format(word), valid=False)

        if fb.isEmpty():
            fb.addItem(title='查询 "{}"'.format(q),
                       subtitle='没有建议，回车直接查词',
                       autocomplete='> {}'.format(q), valid=False)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as ex:
        fb = _error_feedback(q, ex, suggest=True)
    fb.output()


def main(args=None):
    args = sys.argv[1:] if args is None else args
    q = args[0].strip() if args else ''
    lookup = q.startswith('>')
    if lookup:
        q = q[1:].strip()
    if not q:
        fb = Feedback()
        fb.addItem(title='请输入单词或词语', valid=False)
        fb.output()
        return
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/53.0.2785.89 Safari/537.36',
    }
    if lookup:
        get_phonetic_symbols_new(q, headers)
    else:
        get_suggest(q, headers)


if __name__ == '__main__':
    main()

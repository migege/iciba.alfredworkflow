#!/usr/bin/env python
# -*- coding:utf8 -*-

__author__ = 'lzw.whu@gmail.com'
__version__ = '20260719:11'

from alfred.feedback import Feedback
from alfred.core import log
import requests

import sys
import time
import hashlib

_TIMEOUT = 10
ICIBA_PAGE = 'http://www.iciba.com/{}'


def _add_mean_items(fb, word, symbol):
    """把一条 symbol 的释义拆成多个 Feedback item 追加进去。"""
    means = symbol['parts']
    for mean in means:
        if mean.get('part'):
            subtitle = mean['part'] + ' ' + '; '.join(mean['means'])
        else:
            subtitle = '; '.join(mean['means'])
        if 'ph_en' in symbol and 'ph_am' in symbol:
            title = '{word} 英:[{en}] 美:[{am}]'.format(
                word=word, en=symbol['ph_en'], am=symbol['ph_am'])
        elif 'word_symbol' in symbol:
            title = '{word} 拼音:[{word_symbol}]'.format(
                word=word, word_symbol=symbol['word_symbol'])
        else:
            title = word
        fb.addItem(title=title, subtitle=subtitle,
                   arg=ICIBA_PAGE.format(word))


def get_phonetic_symbols_new(word, headers):
    word = word.strip()
    data = [
        ("client", "6"),
        ("key", "1000006"),
        ("timestamp", str(int(time.time() * 1000))),
        ("word", word),
    ]
    url = "https://dict.iciba.com/dictionary/word/query/web"

    # 签名规则:路径 + 各参数值 + 盐
    to_sign = url[len("https:"):].replace("//dict.iciba.com", "")
    for _, v in data:
        to_sign += v
    to_sign += "7ece94d9f9c202b0d2ec557dg4r9bc"
    data.append(("signature", hashlib.md5(to_sign.encode('utf8')).hexdigest()))

    fb = Feedback()
    try:
        r = requests.get(url, params=data, headers=headers, timeout=_TIMEOUT)
        res = r.json()
        base = res["message"]['baesInfo']
    except Exception as ex:
        log('get_phonetic_symbols_new error: {} | word={} | resp={}'.format(
            ex, word, r.text if 'r' in locals() else None))
        fb.addItem(title='查询失败', subtitle=str(ex), valid=False)
        fb.output()
        return

    symbols = base.get('symbols')
    if symbols:
        for symbol in symbols:
            _add_mean_items(fb, word, symbol)

    # 没有词典释义时,回退到接口给出的机器翻译结果
    if fb.isEmpty():
        translate = base.get('translate_result') or ''
        if translate and translate != word:
            fb.addItem(
                title='{word} => {trans}'.format(word=word, trans=translate),
                subtitle=base.get('translate_msg', '机器翻译结果'),
                arg=ICIBA_PAGE.format(word))
        else:
            fb.addItem(title='未找到 "{}"'.format(word),
                       subtitle='回车打开词霸网页查询',
                       arg=ICIBA_PAGE.format(word))
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
    url = 'http://dict-mobile.iciba.com/interface/index.php'
    fb = Feedback()
    try:
        r = requests.get(url, params=params, headers=headers, timeout=_TIMEOUT)
        res = r.json()
        messages = res['message']
    except Exception as ex:
        log('get_suggest error: {} | q={} | resp={}'.format(
            ex, q, r.text if 'r' in locals() else None))
        fb.addItem(title='查询失败', subtitle=str(ex), valid=False)
        fb.output()
        return

    for msg in messages:
        means = msg['means']
        if not means:
            fb.addItem(title=msg['key'],
                       autocomplete='> {}'.format(msg['key']), valid=False)
            continue

        for mean in means:
            if mean.get('part'):
                subtitle = mean['part'] + ' ' + '; '.join(mean['means'])
            else:
                subtitle = '; '.join(mean['means'])
            fb.addItem(title=msg['key'], subtitle=subtitle,
                       arg=ICIBA_PAGE.format(q),
                       autocomplete='> {}'.format(msg['key']), valid=False)

    if fb.isEmpty():
        fb.addItem(title='未找到 "{}" 的建议'.format(q), valid=False)
    fb.output()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit()

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/53.0.2785.89 Safari/537.36',
    }
    q = sys.argv[1]
    if '>' in q:
        q = q.split('>')[-1]
        get_phonetic_symbols_new(q, headers)
    else:
        get_suggest(q, headers)

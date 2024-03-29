#!/usr/bin/env python
# -*- coding:utf8 -*-
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

__author__ = 'lzw.whu@gmail.com'
__version__ = '20220501:10'

from alfred.feedback import Feedback
import requests

import sys
import time
import hashlib
import json

# reload(sys)
# sys.setdefaultencoding('utf8')


def get_phonetic_symbols_new(word, headers):
    word = word.strip()
    # url = "https://dict.iciba.com/dictionary/word/query/web?client=6&key=1000006&timestamp=1628233093905&word=hello&signature=0a78228c59344a8c368f20d47fe6fd2b"
    data = [
        ("client", "6"),
        ("key", "1000006"),
        ("timestamp", str(int(time.time() * 1000))),
        ("word", word),
    ]
    url = "https://dict.iciba.com/dictionary/word/query/web"

    to_sign = url[len("https:"):].replace("//dict.iciba.com", "")
    for k, v in data:
        to_sign += v
    to_sign += "7ece94d9f9c202b0d2ec557dg4r9bc"
    sign = hashlib.md5(to_sign.encode('utf8')).hexdigest()
    data.append(("signature", sign))
    url += "?"
    for k, v in data:
        url += "{k}={v}&".format(k=k, v=v)
    url.rstrip("&")
    r = requests.get(url, headers=headers)
    res = r.json()

    try:
        fb = Feedback()
        msg = res["message"]
        for symbol in msg['baesInfo']['symbols']:
            means = symbol['parts']
            for mean in means:
                if mean['part']:
                    subtitle = mean['part'] + ' ' + '; '.join(mean['means'])
                else:
                    subtitle = '; '.join(mean['means'])
                if 'ph_en' in symbol and 'ph_am' in symbol:
                    title = '{word} 英:[{en}] 美:[{am}]'.format(word=word, en=symbol['ph_en'], am=symbol['ph_am'])
                elif 'word_symbol' in symbol:
                    title = '{word} 拼音:[{word_symbol}]'.format(word=word, word_symbol=symbol['word_symbol'])
                kwargs = {
                    'title': title,
                    'subtitle': subtitle,
                    'arg': 'http://www.iciba.com/%s' % word,
                }
                fb.addItem(**kwargs)
        fb.output()
    except Exception as ex:
        print("EXCEPT:", ex)


def get_phonetic_symbols(word, headers):
    word = word.strip()
    url = 'http://www.iciba.com/index.php?a=getWordMean&c=search&list=1&word=%s' % word
    try:
        r = requests.get(url, headers=headers)
        res = r.json()
        fb = Feedback()
        for symbol in res['baesInfo']['symbols']:
            means = symbol['parts']
            for mean in means:
                if mean['part']:
                    subtitle = mean['part'] + ' ' + '; '.join(mean['means'])
                else:
                    subtitle = '; '.join(mean['means'])
                if 'ph_en' in symbol and 'ph_am' in symbol:
                    title = '{word} 英:[{en}] 美:[{am}]'.format(word=word, en=symbol['ph_en'], am=symbol['ph_am'])
                elif 'word_symbol' in symbol:
                    title = '{word} 拼音:[{word_symbol}]'.format(word=word, word_symbol=symbol['word_symbol'])
                kwargs = {
                    'title': title,
                    'subtitle': subtitle,
                    'arg': 'http://www.iciba.com/%s' % word,
                }
                fb.addItem(**kwargs)
        fb.output()
    except:
        pass


def get_suggest(q, headers):
    q = q.strip()
    url = 'http://dict-mobile.iciba.com/interface/index.php?c=word&m=getsuggest&nums=5&client=6&uid=0&is_need_mean=1&word=%s' % q
    try:
        r = requests.get(url, headers=headers)
        res = r.json()
        fb = Feedback()
        for msg in res['message']:
            means = msg['means']
            if not means:
                kwargs = {
                    'title': msg['key'],
                    'autocomplete': '> %s' % msg['key'],
                    'valid': False,
                }
                fb.addItem(**kwargs)
                continue

            for mean in means:
                if mean['part']:
                    subtitle = mean['part'] + ' ' + '; '.join(mean['means'])
                else:
                    subtitle = '; '.join(mean['means'])
                kwargs = {
                    'title': msg['key'],
                    'subtitle': subtitle,
                    'arg': 'http://www.iciba.com/%s' % q,
                    'autocomplete': '> %s' % msg['key'],
                    'valid': False,
                }
                fb.addItem(**kwargs)
        fb.output()
    except:
        pass


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit()

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/53.0.2785.89 Safari/537.36',
    }
    q = sys.argv[1]
    if '>' in q:
        q = q.split('>')[-1]
        get_phonetic_symbols_new(q, headers)
    else:
        get_suggest(q, headers)

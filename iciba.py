#!/usr/bin/env python
# -*- coding:utf8 -*-
import sys
import os
from alfred.feedback import Feedback
import requests

reload(sys)
sys.setdefaultencoding('utf8')


def run(q):
    q = q.strip()
    url = 'http://dict-mobile.iciba.com/interface/index.php?c=word&m=getsuggest&nums=5&client=6&uid=0&is_need_mean=1&word=%s' % q
    headers = {
        'User-Agent':
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/53.0.2785.89 Safari/537.36',
    }
    try:
        r = requests.get(url, headers=headers)
        res = r.json()
        fb = Feedback()
        for msg in res['message']:
            means = msg['means']
            for mean in means:
                if mean['part']:
                    subtitle = mean['part'] + ' ' + '; '.join(mean['means'])
                else:
                    subtitle = '; '.join(mean['means'])
                kwargs = {
                    'title': msg['key'],
                    'subtitle': subtitle,
                    'arg': 'http://www.iciba.com/%s' % q,
                }
                fb.addItem(**kwargs)
        fb.output()
    except:
        pass


if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit()
    q = sys.argv[1]
    run(q)

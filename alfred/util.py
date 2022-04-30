# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, unicode_literals
import hashlib, random

hashDigest = lambda s: hashlib.md5(s.encode('utf8')).hexdigest()

uid = lambda: hashDigest('{}'.format(random.getrandbits(25)))

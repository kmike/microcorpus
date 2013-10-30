# -*- coding: utf-8 -*-
from __future__ import absolute_import
import codecs
import heapq
import functools
import random


def tolist(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return list(func(*args, **kwargs))
    return wrapper


def iter_lines(filename):
    with codecs.open(filename, 'r', encoding='utf8') as f:
        for line in f:
            yield line.rstrip()


def sample_from_iterable(it, k):
    # see http://stackoverflow.com/questions/12581437/python-random-sample-with-a-generator
    return (x for _, x in heapq.nlargest(k, ((random.random(), x) for x in it)))



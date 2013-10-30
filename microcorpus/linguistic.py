# -*- coding: utf-8 -*-
from __future__ import absolute_import
import pymorphy2
from pymorphy2 import shapes
from pymorphy2.opencorpora_dict.preprocess import tag2grammemes
from pymorphy2.tokenizers import simple_word_tokenize as tokenize
import russian_tagsets
from russian_tagsets.opencorpora import INTERNAL_TO_EXTERNAL, EXTERNAL_TO_INTERNAL

morph = pymorphy2.MorphAnalyzer()


def tag_repr(tag):
    return russian_tagsets.opencorpora.internal_to_external(str(tag))


def grammeme_cyr2lat(grammeme):
    return EXTERNAL_TO_INTERNAL[grammeme.strip()]


def tag_prob(token, tag):
    # FIXME: grammemes order?
    return morph.prob_estimator.p_t_given_w.prob(token.lower(), tag)


def token_is_unknown(token):
    tests = [morph.word_is_known, shapes.is_punctuation, str.isdigit]
    return not any(test(token) for test in tests)

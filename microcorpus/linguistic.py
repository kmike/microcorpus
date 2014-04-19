# -*- coding: utf-8 -*-
from __future__ import absolute_import
from collections import defaultdict
import pymorphy2
from pymorphy2 import shapes
from pymorphy2.opencorpora_dict.preprocess import tag2grammemes
from pymorphy2.tokenizers import simple_word_tokenize as tokenize

morph = pymorphy2.MorphAnalyzer()


def tag_prob(token, tag):
    # FIXME: grammemes order?
    return morph.prob_estimator.p_t_given_w.prob(token.lower(), tag)


def _tag_is_predicted(token):
    tests = [morph.word_is_known, shapes.is_punctuation, str.isdigit]
    return not any(test(token) for test in tests)


class ParseInfo:
    UNIVOCAL = 'univocal'
    AMBIG = 'ambig'
    DISCARDED = 'discarded'

    def __init__(self, tag, normal_form_raw, state):
        self.tag = tag
        self.normal_form_raw = normal_form_raw
        self.state = state

    @property
    def normal_form(self):
        for gr in ['Name', 'Surn', 'Patr', 'Geox', 'Orgn']:
            if gr in self.tag:
                return self.normal_form_raw.title()
        return self.normal_form_raw

    @property
    def grammemes(self):
        return tag2grammemes(self.tag)


class TokenInfo:
    def __init__(self, token, parses, index):
        self.token = token
        self.parses = parses
        self.index = index

    def is_unambig(self):
        return any(p.state == ParseInfo.UNIVOCAL for p in self.parses)

    def all_normal_forms_are_equal(self):
        if not len(self.parses):
            return True
        form0 = self.parses[0].normal_form
        return all(p.normal_form == form0 for p in self.parses)

    def tag_probability(self, tag):
        return tag_prob(self.token, tag)

    def tag_is_predicted(self):
        return _tag_is_predicted(self.token)

    @property
    def grammeme_classes(self):
        return get_grammeme_classes(self.parses)

    @property
    def possible_tags(self):
        return [p.tag for p in _without_discarded(self.parses)]

    # ======= actions ===========

    def select_tag(self, tag):
        self.parses = [ParseInfo(tag, '', ParseInfo.UNIVOCAL)]

    def select_grammeme(self, gr):
        possible_parses = [p for p in self.parses if gr in p.grammemes]

        if gr in self.grammeme_classes[ParseInfo.DISCARDED]:
            for p in possible_parses:
                p.state = ParseInfo.AMBIG

        self.parses = _without_discarded(possible_parses)

    def reset(self):
        parses = morph.parse(self.token)
        state = ParseInfo.AMBIG if len(parses) != 1 else ParseInfo.UNIVOCAL
        self.parses = [
            ParseInfo(p.tag, p.normal_form, state)
            for p in parses
        ]


def _without_discarded(parses):
    return [p for p in parses if p.state != ParseInfo.DISCARDED]


def get_grammeme_classes(parses):
    """ Given a list of ``ParseInfo`` structures, return a dict with its
    grammemes, classified::

        {
            TokenInfo.UNIVOCAL: {set of univocal grammemes},
            TokenInfo.AMBIG: {set of possible grammemes},
            TokenInfo.DISCARDED: {set of discarded grammemes},
        }

    """
    all_grammemes = defaultdict(set)
    tag_grammemes = defaultdict(list)

    for p in parses:
        gr = tag2grammemes(p.tag)
        tag_grammemes[p.state].append((p.tag, gr))
        all_grammemes[p.state] |= gr

    if not all_grammemes[ParseInfo.UNIVOCAL]:
        all_grammemes[ParseInfo.UNIVOCAL] = all_grammemes[ParseInfo.AMBIG].copy()
        for tag, gr in tag_grammemes[ParseInfo.AMBIG]:
            all_grammemes[ParseInfo.UNIVOCAL] &= gr

    all_grammemes[ParseInfo.DISCARDED] -= all_grammemes[ParseInfo.UNIVOCAL]
    all_grammemes[ParseInfo.DISCARDED] -= all_grammemes[ParseInfo.AMBIG]
    all_grammemes[ParseInfo.AMBIG] -= all_grammemes[ParseInfo.UNIVOCAL]
    return dict(all_grammemes)


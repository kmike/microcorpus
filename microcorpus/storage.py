# -*- coding: utf-8 -*-
from __future__ import absolute_import
import os
import tempfile
import hashlib
from .linguistic import morph as default_morph
from .linguistic import ParseInfo, TokenInfo, get_grammeme_classes
from .utils import tolist, sample_from_iterable, iter_lines


class SentenceStorage:
    TAG_SPLITTER = ' / '

    def __init__(self, root, morph=default_morph):
        self.root = root
        self.morph = morph

    def generate_tasks(self, k):
        """
        Select ``k`` random sentences from raw corpus and
        create tasks from them.
        """
        for sent in self._random_sample_sentences(k):
            self._create_task(sent)

    def todo_tasks(self):
        return self._task_list('todo')

    def started_tasks(self):
        return self._task_list('started')

    def done_tasks(self):
        return self._task_list('done')

    def prev_next_started(self, name):
        return self._prev_next_task('started', name)

    @tolist
    def load(self, stage, name):
        """ Load sentence ``name`` from stage ``stage``.
        Return a list of ``TokenInfo`` instances.
        """
        for idx, (token, tags) in enumerate(self._load_raw(stage, name)):
            parses_info = self._get_parses_info(token, tags)
            yield TokenInfo(token, parses_info, idx)

    def write_sent(self, stage, name, sent):
        tokens_tags = [(info.token, info.possible_tags) for info in sent]
        filename = self._path(stage, name)
        self._write_task(filename, tokens_tags)

    def start(self, name):
        self._move('todo', 'started', name)

    def finish(self, name):
        self._move('started', 'done', name)

    def _prev_next_task(self, stage, name):
        tasks = self._task_list(stage)
        idx = tasks.index(name)

        try:
            prev_task = tasks[idx - 1]
        except IndexError:
            prev_task = tasks[-1]

        try:
            next_task = tasks[idx + 1]
        except IndexError:
            next_task = tasks[0]

        return prev_task, next_task

    def _task_list(self, stage):
        return os.listdir(self._path(stage))

    @tolist
    def _load_raw(self, stage, name):
        for line in iter_lines(self._path(stage, name)):
            token, tags = line.split(None, 1)
            tags = [t.strip() for t in tags.split(self.TAG_SPLITTER.strip())]
            yield token, tags

    @tolist
    def _get_parses_info(self, token, tags):
        parses = self.morph.parse(token)
        normal_forms = {str(p.tag): p.normal_form for p in parses}
        extra_tags = set(str(p.tag) for p in parses) - set(tags)
        all_tags = tags + [str(p.tag) for p in parses
                           if str(p.tag) in extra_tags]

        for tag in all_tags:
            normal_form = normal_forms.get(tag, '?')
            if tag in extra_tags:
                yield ParseInfo(tag, normal_form, ParseInfo.DISCARDED)
            elif len(tags) == 1:
                yield ParseInfo(tag, normal_form, ParseInfo.UNIVOCAL)
            else:
                yield ParseInfo(tag, normal_form, ParseInfo.AMBIG)

    def _create_task(self, sent):
        name = hashlib.md5(" ".join(sent).encode('utf8')).hexdigest()[:8]
        filename = self._path('todo', name + '.txt')
        parsed_sent = [
            (token, self.morph.tag(token))
            for token in sent.split()
        ]
        self._write_task(filename, parsed_sent)

    def _write_task(self, filename, parsed_sent):
        with tempfile.NamedTemporaryFile('w', encoding='utf8', delete=False) as f:
            for token, tags in parsed_sent:
                tags = [str(tag) for tag in tags] or ['UNKN']
                line = "%-15s %s\n" % (token, self.TAG_SPLITTER.join(tags))
                f.write(line)
            f.close()
        os.rename(f.name, filename)

    def _random_sample_sentences(self, k):
        fn = self._path("corpus.txt")
        return list(sample_from_iterable(iter_lines(fn), k))

    def _path(self, *args):
        return os.path.abspath(os.path.join(self.root, *args))

    def _rmtask(self, src, name):
        os.unlink(self._path(src, name))

    def _exists(self, *args):
        return os.path.isfile(self._path(*args))

    def _move(self, src, dst, name):
        os.rename(self._path(src, name), self._path(dst, name))



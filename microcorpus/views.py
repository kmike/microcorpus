# coding: utf8
import os
import random
from flask import render_template, abort, request, redirect, url_for, g
from microcorpus import app
from microcorpus.storage import SentenceStorage
from microcorpus import linguistic

DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data')
storage = SentenceStorage(DATA_PATH, linguistic.morph)

@app.route('/')
def index():
    return render_template('index.jinja2')


@app.route('/parse/')
def pymorphy2_parse():
    words = request.args.get('w', '')
    parses = [(w, linguistic.morph.parse(w)) for w in linguistic.tokenize(words)]
    return render_template('parse.jinja2', words=words, parses=parses,
                           tag_repr=linguistic.tag_repr)

@app.route('/random-task/')
def sentence_random():
    task = random.choice(storage.started_tasks())
    return redirect(url_for("sentence", name=task))


@app.route('/started/<name>/')
def sentence(name):
    sent = _started_sent_or_404(name)
    prev, next = storage.prev_next_started(name)
    if 'next' in request.args:
        return redirect(url_for("sentence", name=next))
    if 'prev' in request.args:
        return redirect(url_for("sentence", name=prev))

    sent_info = [_token_info(idx, token_row) for idx, token_row in enumerate(sent)]
    tokens = _sent_tokens(sent)

    return render_template('sentence.jinja2',
        sent=sent_info,
        name=name,
        tokens=tokens,
        unambig_percent=_unambig_percent(tokens)
    )

@app.route('/started/<name>/done', methods=["POST"])
def sentence_done(name):
    prev, next = storage.prev_next_started(name)
    storage.finish(name)
    return redirect(url_for("sentence", name=next))


@app.route('/started/<name>/progress/')
def sentence_progress_percent(name):
    tokens = _sent_tokens(_started_sent_or_404(name))
    return str(_unambig_percent(tokens))


@app.route('/started/<name>/text/')
def sentence_text(name):
    tokens = _sent_tokens(_started_sent_or_404(name))
    return render_template("inc/sentence_text.jinja2",
        tokens=tokens,
        unambig_percent=_unambig_percent(tokens)
    )


@app.route('/started/<sentence_name>/<int:token_index>/', methods=['GET', 'POST'])
def token_tag(sentence_name, token_index):
    if not request.is_xhr:
        return abort(400)

    sent = _started_sent_or_404(sentence_name)
    token_info = _token_info(token_index, sent[token_index])

    if request.method == 'GET':
        return render_template('inc/token_row.jinja2', info=token_info)

    parsed_sent = [[token, tags] for token, tags, grammemes in sent]

    if 'tag' in request.form:
        proper_tag = request.form['tag']
        parsed_sent[token_index][1] = [(proper_tag, '', SentenceStorage.UNIVOCAL)]

    elif 'grammeme' in request.form:
        gr = request.form['grammeme']

        new_cls = None
        if gr in token_info['grammemes'].get(SentenceStorage.DISCARDED, []):
            new_cls = SentenceStorage.AMBIG

        proper_grammeme = linguistic.grammeme_cyr2lat(gr)
        token, tags = parsed_sent[token_index]

        #pymorphy2_tags = set(t.grammemes for t in linguistic.morph.tag(token))

        parsed_sent[token_index][1] = [
            [tag, norm_form, new_cls or cls]
            for tag, norm_form, cls in tags
            if proper_grammeme in linguistic.tag2grammemes(tag)
            #or linguistic.tag2grammemes(tag) not in pymorphy2_tags
        ]

    parsed_sent = _without_discarded_tags(parsed_sent)
    storage.write_sent('started', sentence_name, parsed_sent)
    return redirect(url_for("token_tag", sentence_name=sentence_name, token_index=token_index))


@app.route('/started/<sentence_name>/<int:token_index>/raw/', methods=['POST', 'GET'])
def token_raw_tag(sentence_name, token_index):
    sent = _started_sent_or_404(sentence_name)
    parsed_sent = [[token, tags] for token, tags, grammemes in sent]

    if request.method == 'GET':
        token = parsed_sent[token_index][0]
        return render_template('inc/rawtags.jinja2',
           sentence_name=sentence_name,
           token_index=token_index,
           token=token,
        )

    proper_tag = request.form['tag'].strip()
    if proper_tag:
        parsed_sent[token_index][1] = [(proper_tag, '', SentenceStorage.UNIVOCAL)]
        parsed_sent = _without_discarded_tags(parsed_sent)
        storage.write_sent('started', sentence_name, parsed_sent)

    if request.is_xhr:
        return redirect(url_for("token_tag", sentence_name=sentence_name, token_index=token_index))

    return redirect(url_for("sentence", name=sentence_name))


@app.context_processor
def inject_stats():
    def get_stats():
        stats = getattr(g, 'disambig_stats', None)
        if stats is None:
            done = storage.done_tasks()
            started = storage.started_tasks()
            stats = g.disambig_stats = {
                'done': len(done),
                'started': len(started)
            }
        return stats
    return {'get_stats': get_stats}


def _token_info(idx, token_row):
    token, tags, grammemes = token_row
    CSS_SUFFIXES = {
        SentenceStorage.AMBIG: 'info',
        SentenceStorage.UNIVOCAL: 'primary',
        SentenceStorage.DISCARDED: 'default',
    }

    ambig_grammemes = grammemes.get(SentenceStorage.AMBIG, set())
    all_grammemes = set()
    for gr in grammemes.values():
        all_grammemes |= gr
    help_links = _help_links(token, ambig_grammemes, all_grammemes)

    same_normal_forms = False
    if len(tags) and all(tags[0][1] == t[1] for t in tags):
        same_normal_forms = True

    res = {
        'index': idx,
        'token': token,
        'same_normal_forms': same_normal_forms,
        'tags': [
            (
                norm_form,
                linguistic.tag_repr(tag),
                linguistic.tag_prob(token, tag),
                tag,
                CSS_SUFFIXES[cls],
            )
            for tag, norm_form, cls in tags
        ],
        'grammemes': {cls: sorted(linguistic.tag_repr(g) for g in gr)
                           for cls, gr in grammemes.items()},
        'is_unknown': linguistic.token_is_unknown(token),
        'help_links': help_links,
    }
    return res


def _help_links(token, ambig_grammemes, all_grammemes):
    res = {}
    wiktionary_grammemes = {'ADVB', 'NPRO', 'CONJ', 'PRCL', 'PREP', 'INTJ', 'PRED', 'Apro'}
    if all_grammemes & wiktionary_grammemes:
        res['вики'] = 'http://ru.wiktionary.org/wiki/%s' % token.lower()

    opencorpora_instructions = [
        # Снятие неоднозначности между союзами, частицами и наречиями
        (set(), {'PRCL', 'ADVB'}, 'http://opencorpora.org/manual.php?pool_type=48'),

        # Снятие неоднозначности между наречием и кратким прилагательным
        (set(), {'ADVB', 'ADJS'}, 'http://opencorpora.org/manual.php?pool_type=52'),

        # Снятие неоднозначности между полным прилагательным и местоимением-существительным
        (set(), {'ADJF', 'Apro', 'NPRO'}, 'http://opencorpora.org/manual.php?pool_type=40'),

        # Снятие неоднозначности между союзами, междометиями и частицами
        (set(), {'CONJ', 'INTJ'}, 'http://opencorpora.org/manual.php?pool_type=41'),
        (set(), {'CONJ', 'PRCL'}, 'http://opencorpora.org/manual.php?pool_type=41'),

        # Снятие неоднозначности между именительным и винительным падежами у существительных
        ({'NOUN'}, {'nomn', 'accs'}, 'http://opencorpora.org/manual.php?pool_type=7'),

        # Снятие неоднозначности между родительным и винительным падежом у существительных
        ({'NOUN'}, {'gent', 'accs'}, 'http://opencorpora.org/manual.php?pool_type=6'),

        # Снятие неоднозначности между падежами у прилагательных и причастий единственного числа
        ({'ADJF'}, {'sing'}, 'http://opencorpora.org/manual.php?pool_type=7'),
        ({'PRTF'}, {'sing'}, 'http://opencorpora.org/manual.php?pool_type=7'),
    ]
    for required, ambig, link in opencorpora_instructions:
        if (not required or required & all_grammemes) and ambig <= ambig_grammemes:
            name = "/".join([linguistic.tag_repr(g) for g in ambig])
            if required:
                name = "%s:%s" % (','.join([linguistic.tag_repr(g) for g in required]), name)
            res[name] = link

    return res


def _started_sent_or_404(name):
    try:
        return storage.load('started', name)
    except IOError:
        return abort(404)


def _is_unambig(tags):
    return any([cls == SentenceStorage.UNIVOCAL for t, norm, cls in tags])


def _sent_tokens(sent):
    return [(token, _is_unambig(tags)) for token, tags, grammemes in sent]


def _unambig_percent(tokens):
    unambig_ratio = sum(1 for (t, unambig) in tokens if unambig) / len(tokens)
    return int(unambig_ratio*100)


def _without_discarded_tags(parsed_sent):
    return [
        [token, [tag for tag, norm, cls in tags if cls != SentenceStorage.DISCARDED]]
        for token, tags in parsed_sent
    ]


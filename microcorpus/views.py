# coding: utf8
import os
import random
from flask import render_template, abort, request, redirect, url_for, g
from microcorpus import app
from microcorpus.storage import SentenceStorage
from microcorpus.linguistic import ParseInfo, morph, tokenize

DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data')
storage = SentenceStorage(DATA_PATH, morph)


@app.route('/')
def index():
    return render_template('index.jinja2')


@app.route('/parse/')
def pymorphy2_parse():
    words = request.args.get('w', '')
    parses = [(w, morph.parse(w)) for w in tokenize(words)]
    return render_template('parse.jinja2', words=words, parses=parses,
                           tag_repr=morph.lat2cyr)


@app.route('/random-task/')
def sentence_random():
    task = random.choice(storage.started_tasks())
    return redirect(url_for("sentence", name=task))


@app.route('/started/<name>/')
def sentence(name):
    sent = _started_sent_or_404(name)

    prev_task, next_task = storage.prev_next_started(name)
    if 'next' in request.args:
        return redirect(url_for("sentence", name=next_task))
    if 'prev' in request.args:
        return redirect(url_for("sentence", name=prev_task))

    sent_info = [_token_info_dict(idx, token_info)
                 for idx, token_info in enumerate(sent)]
    tokens = _sent_tokens(sent)

    return render_template('sentence.jinja2',
        sent=sent_info,
        name=name,
        tokens=tokens,
        unambig_percent=_unambig_percent(tokens)
    )


@app.route('/started/<name>/done', methods=["POST"])
def sentence_done(name):
    prev_task, next_task = storage.prev_next_started(name)
    storage.finish(name)
    return redirect(url_for("sentence", name=next_task))


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
    token_info = sent[token_index]

    if request.method == 'GET':
        token_info_dict = _token_info_dict(token_index, token_info)
        return render_template('inc/token_row.jinja2', info=token_info_dict)

    if 'tag' in request.form:  # user selected a tag
        token_info.select_tag(request.form['tag'])

    elif 'grammeme' in request.form:  # user selected a grammeme
        gr = morph.cyr2lat(request.form['grammeme'].strip())
        token_info.select_grammeme(gr)

    storage.write_sent('started', sentence_name, sent)
    url = url_for("token_tag", sentence_name=sentence_name, token_index=token_index)
    return redirect(url)


@app.route('/started/<sentence_name>/<int:token_index>/raw/', methods=['POST', 'GET'])
def token_raw_tag(sentence_name, token_index):
    sent = _started_sent_or_404(sentence_name)
    token_info = sent[token_index]
    #parsed_sent = [[token, tags] for token, tags, grammemes in sent]

    if request.method == 'GET':
        return render_template('inc/rawtags.jinja2',
           sentence_name=sentence_name,
           token_index=token_index,
           token=token_info.token,
        )

    proper_tag = request.form['tag'].strip()
    if proper_tag:
        token_info.select_tag(proper_tag)
        storage.write_sent('started', sentence_name, sent)

    if request.is_xhr:
        url = url_for("token_tag", sentence_name=sentence_name, token_index=token_index)
        return redirect(url)

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


CSS_SUFFIXES = {
    ParseInfo.AMBIG: 'info',
    ParseInfo.UNIVOCAL: 'primary',
    ParseInfo.DISCARDED: 'default',
}


def _token_info_dict(idx, token_info):
    ambig_grammemes = token_info.grammeme_classes[ParseInfo.AMBIG]
    all_grammemes = set()
    for gr in token_info.grammeme_classes.values():
        all_grammemes |= gr
    help_links = _help_links(token_info.token, ambig_grammemes, all_grammemes)

    res = {
        'index': idx,
        'token': token_info.token,
        'same_normal_forms': token_info.all_normal_forms_are_equal(),
        'tags': [
            (
                p.normal_form,
                morph.lat2cyr(p.tag),
                token_info.tag_probability(p.tag),
                p.tag,
                CSS_SUFFIXES[p.state],
            )
            for p in token_info.parses
        ],
        'grammemes': {
            cls: sorted(morph.lat2cyr(g) for g in gr)
            for cls, gr in token_info.grammeme_classes.items()
        },
        'is_unknown': token_info.is_unknown(),
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

        # Прилагательные / причастия
        (set(), {'ADJF', 'PRTF'}, 'http://www.opencorpora.org/wiki/%D0%98%D0%BD%D1%81%D1%82%D1%80%D1%83%D0%BA%D1%86%D0%B8%D1%8F_ADJF_PRTF'),

        # Существительные/прилагательные (фамилии)
        ({'famn'}, {'ADJF', 'NOUN'}, 'http://www.opencorpora.org/wiki/%D0%98%D0%BD%D1%81%D1%82%D1%80%D1%83%D0%BA%D1%86%D0%B8%D1%8F_ADJF_NOUN_%28%D1%84%D0%B0%D0%BC%D0%B8%D0%BB%D0%B8%D1%8F%29'),
    ]
    for required, ambig, link in opencorpora_instructions:
        if (not required or required & all_grammemes) and ambig <= ambig_grammemes:
            name = "/".join(morph.lat2cyr(g) for g in ambig)
            if required:
                condition = ','.join(morph.lat2cyr(g) for g in required)
                name = "%s:%s" % (condition, name)
            res[name] = link

    return res


def _started_sent_or_404(name):
    try:
        return storage.load('started', name)
    except IOError:
        return abort(404)


def _sent_tokens(sent):
    return [(info.token, info.is_unambig()) for info in sent]


def _unambig_percent(tokens):
    unambig_ratio = sum(1 for (t, unambig) in tokens if unambig) / len(tokens)
    return int(unambig_ratio * 100)


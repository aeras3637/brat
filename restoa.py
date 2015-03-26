#!/usr/bin/env python
# vim:set ft=python ts=4 sw=4 sts=4 autoindent:

'''
RESTful Open Annotation server.

Author:     Pontus Stenetorp    <pontus stenetorp se>
Version:    2015-03-23
'''

from datetime import datetime
from itertools import izip
from itertools import tee
from md5 import new as md5
from os import walk
from os.path import dirname
from os.path import join as path_join
from os.path import splitext
from re import compile as re_compile
from re import split as re_split
from sys import path as sys_path
from urlparse import urlparse

from flask import Flask
from flask import Response
from flask import jsonify
from flask import request

sys_path.append(path_join(dirname(__file__), 'server/src'))

from annotation import TextAnnotations
from annotation import TextBoundAnnotation
from config import DATA_DIR
from document import _is_hidden

### Constants
APP = Flask('brat')

API_ROOT = '/api'
DOC_ROOT = API_ROOT + '/documents'
ANNS_ROOT = API_ROOT + '/annotations'

TEXTBOUND_REGEX = re_compile(r'(.*?)/(T[0-9]+)(?:\?|$)')
###

@APP.route('{}/<path:url>/'.format(DOC_ROOT))
def doc(url):
    with open('{}.txt'.format(path_join(DATA_DIR, url))) as doc_txt_f:
        return Response(doc_txt_f.read(), mimetype='text/plain charset=utf8')

def _base_dic():
    return {
        '@context': 'http://www.w3.org/ns/oa.jsonld',
        '@graph': [],
        }

def _fill_graph(doc_abspath, graph=None):
    if graph is None:
        graph = []
    doc_relpath = doc_abspath[doc_abspath.find(DATA_DIR) +
        len(DATA_DIR):].lstrip('/')
    base_url = 'http://{}'.format(request.host)
    doc_url = '{}/{}/{}'.format(base_url, DOC_ROOT.lstrip('/'), doc_relpath)
    anns_url = '{}/{}/{}'.format(base_url, ANNS_ROOT.lstrip('/'), doc_relpath)
    with open('{}.txt'.format(doc_abspath)) as doc_text_f:
        doc_text = doc_text_f.read()
    with TextAnnotations(doc_abspath) as ann_obj:
        for ann in ann_obj:
            if not isinstance(ann, TextBoundAnnotation):
                continue # TODO: Raise a warning that we ignore data.
            # TODO: Ignore discontinuous, due to poor client support.
            start = ann.first_start()
            end = ann.last_end()
            graph.append({
                '@type': 'http://www.w3.org/ns/oa#Annotation',
                '@id': '{}/{}/'.format(anns_url, ann.id),
                'target': '{}/#char={},{}'.format(doc_url, start, end),
                'body': ann.type,
                'serializedAt': datetime.utcnow().isoformat(),
                'annotatedAt': datetime.fromtimestamp(0).isoformat(),
                'annotatedBy': 'brat',
                })
    return graph

@APP.route('{}/'.format(ANNS_ROOT))
def anns():
    dic = _base_dic()
    graph = dic['@graph']
    for root, dnames, fnames in walk(DATA_DIR):
        for fname in fnames:
            if not fname.endswith('.ann') or _is_hidden(fname):
                continue
            doc = splitext(fname)[0]
            doc_abspath = path_join(root, doc)
            _fill_graph(doc_abspath, graph=graph)
    return jsonify(dic)

@APP.route('{}/<path:url>/'.format(ANNS_ROOT))
def ann(url):
    m = TEXTBOUND_REGEX.match(url)
    if m:
        doc_url, _id = m.groups()
        doc_abspath = path_join(DATA_DIR, doc_url)
        for ann in _fill_graph(doc_abspath):
            if ann['@id'].endswith('{}/'.format(_id)):
                return jsonify(ann)
    else:
        dic = _base_dic()
        doc_abspath = path_join(DATA_DIR, url)
        _fill_graph(doc_abspath, dic['@graph'])
        return jsonify(dic)

def _pairwise(it):
    a, b = tee(it)
    next(b, None)
    return izip(a, b)

def add_or_update_ann(method):
    req_json = request.get_json(force=True)
    tgt_soup = urlparse(req_json['target'])
    spans = tuple(_pairwise(map(int,
        tgt_soup.fragment.split('=')[1].split(','))))
    doc = tgt_soup.path[len(DOC_ROOT):].lstrip('/')
    doc_abspath = path_join(DATA_DIR, doc).rstrip('/')
    with TextAnnotations(doc_abspath) as ann_obj:
        if method == 'POST':
            _id = ann_obj.get_new_id('T')
            ann = TextBoundAnnotation(spans, _id, req_json['body'], '')
            ann_obj.add_annotation(ann)
        elif method == 'PUT':
            # There is a redundancy here, we could get the ID from the URL.
            _id = req_json['@id'].rstrip('/').split('/')[-1]
            for ann in ann_obj:
                if ann.id != _id:
                    continue
                ann.spans = spans
                ann.type = req_json['body']
                ann.text = ''
                break
            else:
                return ('', 404, )
        else:
            assert False, 'Unknown method'
    for ann in _fill_graph(doc_abspath):
        if not ann['@id'].endswith('{}/'.format(_id)):
            continue
        return jsonify(ann)
    else:
        pass # Annotation not found.

@APP.route('{}/'.format(ANNS_ROOT), methods=('POST', ))
def add_ann():
    return add_or_update_ann('POST')

@APP.route('{}/<path:url>/'.format(ANNS_ROOT), methods=('PUT', ))
def update_ann(url):
    return add_or_update_ann('PUT')

@APP.route('{}/<path:url>/'.format(ANNS_ROOT), methods=('DELETE', ))
def del_ann(url):
    m = TEXTBOUND_REGEX.match(url)
    if m:
        doc_url, _id = m.groups()
        doc_abspath = path_join(DATA_DIR, doc_url)
        with TextAnnotations(doc_abspath) as ann_obj:
            for ann in ann_obj:
                if ann.id != _id:
                    continue
                ann_obj.del_annotation(ann)
                break
            else:
                pass # TODO: ID not found.
        return ('', 204, )
    else:
        pass # TODO: We do not support the deletion of documents.

def main(argv):
    print 'WARNING: No security features, only use for localhost.'
    APP.run(host='localhost', port=47111, debug=True)

if __name__ == '__main__':
    from sys import argv
    exit(main(argv))

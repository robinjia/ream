#!/usr/bin/env python3
"""Ream: A Paper Manager."""
import argparse
from bs4 import BeautifulSoup
from datetime import datetime
import flask
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import re
import sys
import urllib
from xml.etree import ElementTree

import util

QUEUE_PRIORITIES = ['High', 'Medium', 'Low']
READ_STATUSES = ['Intro', 'Partial', 'Skim', 'Read']

# Paper metadata parsing
ARXIV_REGEX = r'/[a-z]+/([0-9]+\.[0-9]+)([^0-9].*)?'
VENUES = [
        'ACL', 'TACL', 'Findings of EMNLP', 'EMNLP', 'NAACL', 'EACL', 'AACL', 'CoNLL', 'COLING', 'LREC' # NLP
        'ICML', 'NIPS', 'NeurIPS', 'ICLR', 'JMLR', 'COLT', 'UAI', 'AISTATS', 'ECML' # ML
        'AAAI', 'IJCAI', 'JAIR', # AI
        'CVPR', 'ICCV', 'ECCV',  # CV
        'ICRA', 'IROS',  # Robotics
        'CIKM', 'KDD', 'VLDB', 'WSDM', 'FOCS', 'STOC', 'ITCS', 'SIGIR', 'UIST', 'ICASSP', # Other
        'SODA', 'CHI', 'RSS', 'WWW'  # Potentially ambiguous
]
VENUE_NAME_MAP = {
        'NIPS': 'NeurIPS'  # Rename NIPS to NeurIPS but match on NIPS for backwards compatibility
}
ACL_ANTHOLOGY_REGEX = r'/anthology/([^/]*)/?'

app = Flask(__name__, root_path=util.ROOT_DIR)
config = util.load_config()
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///{}'.format(config["db_file"])
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class QueuedPaper(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    authors = db.Column(db.String(1024))
    title = db.Column(db.String(1024))
    venue = db.Column(db.String(1024))
    year = db.Column(db.Integer)
    date_added = db.Column(db.DateTime, nullable=False, default=datetime.now)
    priority = db.Column(db.Integer, nullable=False)
    url = db.Column(db.String(1024))

class ReadPaper(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    authors = db.Column(db.String(1024))
    title = db.Column(db.String(1024))
    venue = db.Column(db.String(1024))
    year = db.Column(db.Integer)
    date_added = db.Column(db.DateTime, nullable=False)
    date_read = db.Column(db.DateTime, nullable=False, default=datetime.now)
    status = db.Column(db.Integer, nullable=False)
    url = db.Column(db.String(1024))
    note = db.Column(db.String(65535))

def _parse_arxiv_id(url):
    match = re.match(ARXIV_REGEX, url.path)
    if match:
        return match.group(1)
    return None

def _guess_venue(comment):
    print(comment)
    comment_lower = comment.lower()
    comment_tokens = comment_lower.replace('-', ' ').split()  # Split on '-' for things like ACL-IJCNLP
    print(comment_tokens)
    has_workshop = 'workshop' in comment_tokens
    for v in VENUES:
        if (' ' in v and v.lower() in comment_lower) or v.lower() in comment_tokens:
            # Multi-word just has to match in string, single token has to match token
            venue = v
            break
    else:
        return None
    if venue in VENUE_NAME_MAP:
        venue = VENUE_NAME_MAP[venue]
    if has_workshop:
        return '{} WS'.format(venue)
    return venue

def _parse_arxiv(arxiv_id):
    metadata = {
            'authors': [],
            'url': 'https://arxiv.org/pdf/{}.pdf'.format(arxiv_id),
            'venue': 'arXiv',
    }
    with urllib.request.urlopen('http://export.arxiv.org/api/query?id_list={}'.format(arxiv_id)) as url:
        r = url.read()
    tree = ElementTree.fromstring(r)
    for e in tree:
        if e.tag == '{http://www.w3.org/2005/Atom}entry':
            for child in e:
                if child.tag == '{http://www.w3.org/2005/Atom}updated':
                    metadata['year'] = int(child.text.split('-')[0])
                elif child.tag == '{http://www.w3.org/2005/Atom}title':
                    metadata['title'] = child.text
                elif child.tag == '{http://www.w3.org/2005/Atom}author':
                    for name in child:
                        if name.tag == '{http://www.w3.org/2005/Atom}name':
                            metadata['authors'].append(name.text)
                elif child.tag == '{http://arxiv.org/schemas/atom}comment':
                    # Use heuristics to guess where it was published
                    new_venue = _guess_venue(child.text)
                    if new_venue:
                        metadata['venue'] = new_venue
    metadata['authors'] = ', '.join(metadata['authors'])
    return metadata

def _parse_acl_anthology_id(url):
    match = re.match(ACL_ANTHOLOGY_REGEX, url.path)
    if match:
        anthology_id = match.group(1)
        if anthology_id.endswith('.pdf'):
            anthology_id = anthology_id[:-4] 
        return anthology_id
    return None

def _parse_acl_anthology(anthology_id):
    metadata = {
            'authors': [],
            'url': 'https://www.aclweb.org/anthology/{}.pdf'.format(anthology_id),
    }
    # Use the MODS XML format for most things
    with urllib.request.urlopen('https://www.aclweb.org/anthology/{}.xml'.format(anthology_id)) as url:
        xml = url.read()
    tree = ElementTree.fromstring(xml)
    for e in tree[0]:
        if e.tag == '{http://www.loc.gov/mods/v3}titleInfo':
            metadata['title'] = e[0].text
        elif e.tag == '{http://www.loc.gov/mods/v3}originInfo':
            metadata['year'] = int(e[0].text[:4])  # Always starts with year
        elif e.tag == '{http://www.loc.gov/mods/v3}name':
            role = e.find('{http://www.loc.gov/mods/v3}role')
            role_term = role.find('{http://www.loc.gov/mods/v3}roleTerm')
            if role_term.text == 'author':
                # Not sure what else it can be, but check that this is an author
                name = []
                for np in e.findall('{http://www.loc.gov/mods/v3}namePart'):
                    if len(np.text) == 1:
                        name.append('{}.'.format(np.text))  # Guess that there should be a dot here
                    else:
                        name.append(np.text)
                metadata['authors'].append(' '.join(name))
    metadata['authors'] = ', '.join(metadata['authors'])

    # Use the anthology main page for venue abbreviations
    with urllib.request.urlopen('https://www.aclweb.org/anthology/{}'.format(anthology_id)) as url:
        r = url.read()
    soup = BeautifulSoup(r, 'html.parser')
    links = soup.find_all('a')
    for link in links:
        if link.get('href').startswith('/anthology/venues/'):
            metadata['venue'] = link.get_text()
            break
    return metadata
         
def get_metadata(raw_url):
    """Try to get metadata for given paper URL.

    Returns dict with metadata if successful, or None if failed.
    """
    url = urllib.parse.urlparse(raw_url)
    print(url.netloc)
    if url.netloc.endswith('arxiv.org'):
        arxiv_id = _parse_arxiv_id(url)
        if arxiv_id:
            return _parse_arxiv(arxiv_id)
    elif url.netloc.endswith('aclweb.org'):
        anthology_id = _parse_acl_anthology_id(url)
        print(anthology_id)
        if anthology_id:
            return _parse_acl_anthology(anthology_id)
    return None

@app.route('/', methods=['get'])
def home():
    queued_papers = QueuedPaper.query.order_by(
            QueuedPaper.priority, QueuedPaper.date_added.desc()).all()
    read_papers = ReadPaper.query.order_by(ReadPaper.date_read.desc()).all()
    return flask.render_template(
            'index.html', queued_papers=queued_papers, read_papers=read_papers,
            priorities=QUEUE_PRIORITIES, statuses=READ_STATUSES)

@app.route('/post_add_url', methods=['post'])
def post_add_url():
    priority = int(flask.request.form['priority'])
    metadata = get_metadata(flask.request.form['url'])
    if metadata:
        paper = QueuedPaper(priority=priority, **metadata)
        db.session.add(paper)
        db.session.commit()
        return flask.redirect('/')
    # TODO: error handling
    return flask.redirect('/')

@app.route('/delete_queued', methods=['post'])
def delete_queued():
    paper_id = int(flask.request.form['paper_id'])
    paper = QueuedPaper.query.get(paper_id)
    db.session.delete(paper)
    db.session.commit()
    return flask.redirect('/')

@app.route('/edit_queued/<paper_id>', methods=['get'])
def edit_queued(paper_id):
    paper = QueuedPaper.query.get(paper_id)
    return flask.render_template(
        'queued.html', paper=paper, priorities=QUEUE_PRIORITIES)

@app.route('/post_edit_queued', methods=['post'])
def post_edit_queued():
    paper_id = int(flask.request.form['paper_id'])
    paper = QueuedPaper.query.get(paper_id)
    paper.authors = flask.request.form['authors']
    paper.title = flask.request.form['title']
    paper.venue = flask.request.form['venue']
    paper.year = flask.request.form['year']
    paper.priority = flask.request.form['priority']
    paper.url = flask.request.form['url']
    db.session.commit()
    return flask.redirect('/')

@app.route('/add_read/<paper_id>', methods=['get'])
def add_read(paper_id):
    paper = QueuedPaper.query.get(paper_id)
    return flask.render_template(
            'read.html', paper=paper, statuses=READ_STATUSES, action='post_add_read')

@app.route('/post_add_read', methods=['post'])
def post_add_read():
    paper_id = int(flask.request.form['paper_id'])
    old_paper = QueuedPaper.query.get(paper_id)
    new_paper = ReadPaper(
            authors=flask.request.form['authors'],
            title=flask.request.form['title'],
            venue=flask.request.form['venue'],
            year=flask.request.form['year'],
            date_added=datetime.fromtimestamp(float(flask.request.form['date_added'])),
            status=flask.request.form['status'],
            url=flask.request.form['url'],
            note=flask.request.form['note'])
    db.session.delete(old_paper)
    db.session.add(new_paper)
    db.session.commit()
    return flask.redirect('/')

@app.route('/delete_read', methods=['post'])
def delete_read():
    paper_id = int(flask.request.form['paper_id'])
    paper = ReadPaper.query.get(paper_id)
    db.session.delete(paper)
    db.session.commit()
    return flask.redirect('/')

@app.route('/edit_read/<paper_id>', methods=['get'])
def edit_read(paper_id):
    paper = ReadPaper.query.get(paper_id)
    return flask.render_template(
            'read.html', paper=paper, statuses=READ_STATUSES, action='post_edit_read')

@app.route('/post_edit_read', methods=['post'])
def post_edit_read():
    paper_id = int(flask.request.form['paper_id'])
    paper = ReadPaper.query.get(paper_id)
    paper.authors = flask.request.form['authors']
    paper.title = flask.request.form['title']
    paper.venue = flask.request.form['venue']
    paper.year = flask.request.form['year']
    paper.status = flask.request.form['status']
    paper.url = flask.request.form['url']
    paper.note = flask.request.form['note']
    db.session.commit()
    return flask.redirect('/')


if __name__ == '__main__':
    parser = argparse.ArgumentParser('Launch a Ream server.')
    parser.add_argument('--hostname', '-n', default='0.0.0.0')
    parser.add_argument('--port', '-p', type=int, default=5538)
    parser.add_argument('--debug', '-d', action='store_true')
    args = parser.parse_args()
    if args.debug:
        app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.run(args.hostname, args.port, args.debug)

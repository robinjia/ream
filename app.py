#!/usr/bin/env python3
"""Ream: A Paper Manager."""
import argparse
import bcrypt
from bs4 import BeautifulSoup
from datetime import datetime
import flask
from flask import Flask, request, session
from flaskext.markdown import Markdown
from flask_sqlalchemy import SQLAlchemy
import logging
import re
import sys
import time
import urllib
from xml.etree import ElementTree

import util

QUEUE_PRIORITIES = ['High', 'Medium', 'Low']
READ_STATUSES = ['Intro', 'Partial', 'Skim', 'Read']

# Paper metadata parsing
ARXIV_REGEX = r'/[a-z]+/([0-9]+\.[0-9]+)([^0-9].*)?'
VENUES = [
        'Findings of ACL', 'Findings of EMNLP', 'Findings of NAACL',  # NLP Findings
        'TACL', 'ACL', 'EMNLP', 'NAACL', 'EACL', 'AACL', 'CoNLL', 'COLING', 'LREC' # NLP
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
ACL_ANTHOLOGY_ACLWEB_REGEX = r'/anthology/([^/]*)/?'
ACL_ANTHOLOGY_ORG_REGEX = r'/([^/]*)/?'

app = Flask(__name__, root_path=util.ROOT_DIR)
Markdown(app)
config = util.load_config()
app.config['SECRET_KEY'] = config['secret_key']
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///{}'.format(config['db_file'])
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
logging.basicConfig(format='[%(asctime)s] %(message)s', filename='/tmp/ream_app_log', level=logging.DEBUG)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    queued_papers = db.relationship('QueuedPaper', backref='user', lazy=True)
    read_papers = db.relationship('ReadPaper', backref='user', lazy=True)

class QueuedPaper(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    authors = db.Column(db.String(1024), default='')
    title = db.Column(db.String(1024), default='')
    venue = db.Column(db.String(1024), default='')
    year = db.Column(db.Integer, default=-1)
    date_added = db.Column(db.DateTime, nullable=False, default=datetime.now)
    priority = db.Column(db.Integer, nullable=False)
    url = db.Column(db.String(1024))

class ReadPaper(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
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
    if url.netloc.endswith('aclweb.org'):
        match = re.match(ACL_ANTHOLOGY_ACLWEB_REGEX, url.path)
    elif url.netloc.endswith('aclanthology.org'):
        match = re.match(ACL_ANTHOLOGY_ORG_REGEX, url.path)
    else:
        return None
    if match:
        anthology_id = match.group(1)
        if anthology_id.endswith('.pdf'):
            anthology_id = anthology_id[:-4] 
        return anthology_id
    return None

def _parse_acl_anthology(anthology_id):
    metadata = {
            'authors': [],
            'url': 'https://www.aclanthology.org/{}.pdf'.format(anthology_id),
    }
    # Use the MODS XML format for most things
    with urllib.request.urlopen('https://www.aclanthology.org/{}.xml'.format(anthology_id)) as url:
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
    with urllib.request.urlopen('https://www.aclanthology.org/{}'.format(anthology_id)) as url:
        r = url.read()
    soup = BeautifulSoup(r, 'html.parser')
    links = soup.find_all('a')
    for link in links:
        if link.get('href').startswith('/venues/'):
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
    elif url.netloc.endswith('aclweb.org') or url.netloc.endswith('aclanthology.org'):
        anthology_id = _parse_acl_anthology_id(url)
        print(anthology_id)
        if anthology_id:
            return _parse_acl_anthology(anthology_id)
    return None

def get_paper(model, paper_id):
    """Get paper, checking for user permissions.

    Returns None if user is not logged in.
    Aborts with 403 error if logged in as wrong user.
    Aborts with 404 error if paper is not found.
    """
    if 'user_id' not in flask.session:
        return None
    user_id = flask.session['user_id']
    paper = model.query.get(paper_id)
    if not paper:
        flask.abort(404)
    if paper.user_id != user_id:
        flask.abort(403)
    return paper

@app.route('/', methods=['get'])
def home():
    if 'user_id' in flask.session:
        t0 = time.time()
        user = User.query.get(flask.session['user_id'])
        queued_papers = QueuedPaper.query.filter_by(user_id=user.id).order_by(
                QueuedPaper.priority, QueuedPaper.date_added.desc()).all()
        read_papers = ReadPaper.query.filter_by(user_id=user.id).order_by(
                ReadPaper.date_read.desc()).all()
        t1 = time.time()
        logging.debug('Query time: {}s'.format(t1 - t0))
        if 'focus' in session:
            focus = session['focus']
            focus_id = session['focus_id']
            session.pop('focus', None)
            session.pop('focus_id', None)
        else:
            focus = ''
            focus_id = ''
        return flask.render_template(
                'home.html', queued_papers=queued_papers, read_papers=read_papers,
                priorities=QUEUE_PRIORITIES, statuses=READ_STATUSES,
                focus=focus, focus_id=focus_id)
    else:
        return flask.render_template('login.html')

@app.route('/post_login', methods=['post'])
def post_login():
    username = flask.request.form['username']
    password = flask.request.form['password']
    user = User.query.filter_by(username=username).first()
    if user is None:
        flask.flash('Error: Username not found.')
        return flask.render_template('login.html')
    if not bcrypt.checkpw(password.encode(), user.password_hash):
        flask.flash('Error: Username and password did not match.')
        return flask.render_template('login.html')
    flask.session['user_id'] = user.id
    return flask.redirect('/')

@app.route('/post_logout', methods=['post'])
def post_logout():
    flask.session.pop('user_id', None)
    return flask.redirect('/')

@app.route('/add_user', methods=['get'])
def add_user():
    return flask.render_template('adduser.html')

@app.route('/post_add_user', methods=['post'])
def post_add_user():
    username = flask.request.form['username']
    password = flask.request.form['password']
    if not username:
        flask.flash('Error: Username cannot be empty.')
        return flask.render_template('adduser.html')
    if not password:
        flask.flash('Error: Password cannot be empty.')
        return flask.render_template('adduser.html')
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
    user = User(username=username, password_hash=password_hash)
    db.session.add(user)
    db.session.commit()
    flask.session['user_id'] = user.id
    return flask.redirect('/')

@app.route('/post_add_url', methods=['post'])
def post_add_url():
    if 'user_id' not in flask.session:
        return flask.redirect('/')
    user_id = flask.session['user_id']
    priority = int(flask.request.form['priority'])
    url = flask.request.form['url']
    metadata = get_metadata(url)
    if metadata:
        paper = QueuedPaper(user_id=user_id, priority=priority, **metadata)
        db.session.add(paper)
        db.session.commit()
        session['focus'] = 'queued'
        session['focus_id'] = paper.id
        return flask.redirect('/')
    paper = QueuedPaper(user_id=user_id, priority=priority, url=url)
    db.session.add(paper)
    db.session.commit()
    return flask.redirect('/edit_queued/{}'.format(paper.id))

@app.route('/delete_queued', methods=['post'])
def delete_queued():
    paper = get_paper(QueuedPaper, int(flask.request.form['paper_id']))
    if not paper:
        return flask.redirect('/')
    db.session.delete(paper)
    db.session.commit()
    return flask.redirect('/')

@app.route('/edit_queued/<paper_id>', methods=['get'])
def edit_queued(paper_id):
    paper = get_paper(QueuedPaper, paper_id)
    if not paper:
        return flask.redirect('/')
    return flask.render_template(
        'queued.html', paper=paper, priorities=QUEUE_PRIORITIES)

@app.route('/post_edit_queued', methods=['post'])
def post_edit_queued():
    paper = get_paper(QueuedPaper, int(flask.request.form['paper_id']))
    if not paper:
        return flask.redirect('/')
    paper.authors = flask.request.form['authors']
    paper.title = flask.request.form['title']
    paper.venue = flask.request.form['venue']
    paper.year = flask.request.form['year']
    paper.priority = flask.request.form['priority']
    paper.url = flask.request.form['url']
    db.session.commit()
    session['focus'] = 'queued'
    session['focus_id'] = paper.id
    return flask.redirect('/')

@app.route('/add_read/<paper_id>', methods=['get'])
def add_read(paper_id):
    paper = get_paper(QueuedPaper, paper_id)
    if not paper:
        return flask.redirect('/')
    return flask.render_template(
            'read.html', paper=paper, statuses=READ_STATUSES, action='post_add_read')

@app.route('/post_add_read', methods=['post'])
def post_add_read():
    old_paper = get_paper(QueuedPaper, int(flask.request.form['paper_id']))
    if not old_paper:
        return flask.redirect('/')
    new_paper = ReadPaper(
            user_id = flask.session['user_id'],
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
    session['focus'] = 'read'
    session['focus_id'] = new_paper.id
    return flask.redirect('/')

@app.route('/delete_read', methods=['post'])
def delete_read():
    paper = get_paper(ReadPaper, int(flask.request.form['paper_id']))
    if not paper:
        return flask.redirect('/')
    db.session.delete(paper)
    db.session.commit()
    return flask.redirect('/')

@app.route('/edit_read/<paper_id>', methods=['get'])
def edit_read(paper_id):
    paper = get_paper(ReadPaper, paper_id)
    if not paper:
        return flask.redirect('/')
    return flask.render_template(
            'read.html', paper=paper, statuses=READ_STATUSES, action='post_edit_read')

@app.route('/post_edit_read', methods=['post'])
def post_edit_read():
    paper = get_paper(ReadPaper, int(flask.request.form['paper_id']))
    if not paper:
        return flask.redirect('/')
    paper.authors = flask.request.form['authors']
    paper.title = flask.request.form['title']
    paper.venue = flask.request.form['venue']
    paper.year = flask.request.form['year']
    paper.status = flask.request.form['status']
    paper.url = flask.request.form['url']
    paper.note = flask.request.form['note']
    db.session.commit()
    session['focus'] = 'read'
    session['focus_id'] = paper.id
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

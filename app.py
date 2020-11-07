#!/usr/bin/env python3
"""Ream: A Paper Manager."""
import argparse
from datetime import datetime
import flask
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
import sys
import urllib
from xml.etree import ElementTree

import util

app = Flask(__name__, root_path=util.ROOT_DIR)
config = util.load_config()
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{config["db_file"]}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

QUEUE_PRIORITIES = ['High', 'Medium', 'Low']
READ_STATUSES = ['Intro', 'Partial', 'Skim', 'Read']
EPOCH_START = datetime(1970,1,1)


class QueuedPaper(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    authors = db.Column(db.String(1024), nullable=False)
    title = db.Column(db.String(1024), nullable=False)
    venue = db.Column(db.String(1024), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    date_added = db.Column(db.DateTime, nullable=False, default=datetime.now)
    priority = db.Column(db.Integer, nullable=False)
    url = db.Column(db.String(1024), nullable=False)

class ReadPaper(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    authors = db.Column(db.String(1024), nullable=False)
    title = db.Column(db.String(1024), nullable=False)
    venue = db.Column(db.String(1024), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    date_added = db.Column(db.DateTime, nullable=False)
    date_read = db.Column(db.DateTime, nullable=False, default=datetime.now)
    status = db.Column(db.Integer, nullable=False)
    url = db.Column(db.String(1024), nullable=False)
    note = db.Column(db.String(65535))

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
    arxiv_id = flask.request.form['url']
    priority = int(flask.request.form['priority'])
    with urllib.request.urlopen(f'http://export.arxiv.org/api/query?id_list={arxiv_id}') as url:
        r = url.read()
    tree = ElementTree.fromstring(r)
    metadata = {
            'authors': [],
            'url': f'http://arxiv.org/pdf/{arxiv_id}.pdf',
            'venue': 'arXiv',
            'priority': priority,
    }
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
    metadata['authors'] = ', '.join(metadata['authors'])
    paper = QueuedPaper(**metadata)
    db.session.add(paper)
    db.session.commit()
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
            #id=paper_id,
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

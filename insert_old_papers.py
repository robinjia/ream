"""Insert papers from old DB into new DB under a given username."""
import argparse
import sqlite3
import sys

from app import db, User, QueuedPaper, ReadPaper

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('username')
    parser.add_argument('old_db_file')
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(1)
    return parser.parse_args()

def main(username, old_db_file):
    user = User.query.filter_by(username=username).first()
    if not user:
        raise ValueError(f'Username {username} not found.')
    
    # Connect to the old DB
    con = sqlite3.connect(old_db_file,
                          detect_types=sqlite3.PARSE_DECLTYPES | 
                                       sqlite3.PARSE_COLNAMES)
    cur = con.cursor()

    # Add queued papers 
    queued_papers = cur.execute('SELECT authors, title, venue, year, date_added as "[timestamp]", priority, url FROM queued_paper;')
    for row in queued_papers:
        new_paper = QueuedPaper(
                user_id = user.id,
                authors = row[0],
                title = row[1],
                venue = row[2],
                year = row[3],
                date_added = row[4],
                priority = row[5],
                url = row[6])
        db.session.add(new_paper)

    # Add read papers
    read_papers = cur.execute('SELECT authors, title, venue, year, date_added as "[timestamp]", date_read as "[timestamp]",status, url, note FROM read_paper;')
    for row in read_papers:
        new_paper = ReadPaper(
                user_id = user.id,
                authors = row[0],
                title = row[1],
                venue = row[2],
                year = row[3],
                date_added = row[4],
                date_read = row[5],
                status = row[6],
                url = row[7],
                note = row[8])
        db.session.add(new_paper)

    db.session.commit()
    con.close()

if __name__ == '__main__':
  args = parse_args()
  main(args.username, args.old_db_file)

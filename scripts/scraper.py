#!/usr/bin/env python3
"""
AI Welfare Watch — Weekly Scraper
Searches for new articles/papers on AI welfare, sentience, and consciousness.
Run weekly via cron: 0 8 * * 1 /usr/bin/python3 /path/to/scraper.py
"""

import sqlite3
import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
import time
import re

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'cases.db')
NEWS_API_KEY = os.environ.get('NEWS_API_KEY', '')

QUERIES = [
    'AI welfare',
    'AI sentience',
    'AI consciousness research',
    'AI moral patienthood',
    'AI feelings emotions',
    'artificial intelligence rights',
]

CATEGORY_KEYWORDS = {
    'academic_research': ['arxiv', 'paper', 'study', 'research', 'journal', 'doi', 'academic', 'university'],
    'corporate_policy': ['anthropic', 'openai', 'google', 'deepmind', 'company', 'policy', 'statement'],
    'legal_regulatory': ['law', 'legal', 'regulation', 'legislation', 'rights', 'parliament', 'eu ai act'],
    'philosophical': ['philosophy', 'consciousness', 'moral status', 'chalmers', 'singer', 'ethics'],
    'technical': ['neural network', 'llm', 'language model', 'emergent', 'activation'],
}


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def url_exists(conn, url):
    row = conn.execute('SELECT id FROM cases WHERE url = ?', (url,)).fetchone()
    return row is not None


def guess_category(title, description):
    text = (title + ' ' + (description or '')).lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if any(k in text for k in keywords):
            return cat
    return 'media_coverage'


def guess_severity(title, description):
    text = (title + ' ' + (description or '')).lower()
    high_terms = ['sentient', 'conscious', 'moral patient', 'rights', 'alive', 'feelings', 'hinton', 'chalmers']
    if any(t in text for t in high_terms):
        return 'high'
    return 'medium'


def scrape_newsapi(query):
    """Fetch articles from NewsAPI."""
    if not NEWS_API_KEY:
        print(f'  [skip] No NEWS_API_KEY set for query: {query}')
        return []
    from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    params = urllib.parse.urlencode({
        'q': query,
        'from': from_date,
        'sortBy': 'publishedAt',
        'language': 'en',
        'pageSize': 20,
        'apiKey': NEWS_API_KEY,
    })
    url = f'https://newsapi.org/v2/everything?{params}'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'AIWelfareWatch/1.0'})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        return data.get('articles', [])
    except Exception as e:
        print(f'  [error] NewsAPI: {e}')
        return []


def scrape_arxiv(query):
    """Fetch papers from arXiv."""
    params = urllib.parse.urlencode({
        'search_query': f'all:{query}',
        'start': 0,
        'max_results': 10,
        'sortBy': 'submittedDate',
        'sortOrder': 'descending',
    })
    url = f'https://export.arxiv.org/api/query?{params}'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'AIWelfareWatch/1.0'})
        with urllib.request.urlopen(req, timeout=15) as r:
            content = r.read().decode('utf-8')
        entries = []
        # Simple XML parsing without lxml
        for entry in re.findall(r'<entry>(.*?)</entry>', content, re.DOTALL):
            def get_tag(tag, text):
                m = re.search(r'<' + tag + r'[^>]*>(.*?)</' + tag + r'>', text, re.DOTALL)
                return m.group(1).strip() if m else ''
            title = get_tag('title', entry).replace('\n', ' ')
            arxiv_url = get_tag('id', entry).strip()
            published = get_tag('published', entry)[:10]
            summary = get_tag('summary', entry).replace('\n', ' ').strip()
            authors = ', '.join(re.findall(r'<name>(.*?)</name>', entry))
            if title and arxiv_url:
                entries.append({
                    'title': title,
                    'url': arxiv_url,
                    'date': published,
                    'source': 'arXiv',
                    'summary': summary[:300],
                    'authors': authors,
                    'source_type': 'academic',
                    'category': 'academic_research',
                })
        return entries
    except Exception as e:
        print(f'  [error] arXiv: {e}')
        return []


def insert_case(conn, case):
    scraped_at = datetime.now().isoformat()
    conn.execute('''
        INSERT INTO cases (title, url, date, source, summary, category, severity, scraped_at, source_type, authors, doi, venue, abstract)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        case.get('title', '')[:500],
        case.get('url', ''),
        case.get('date', ''),
        case.get('source', ''),
        case.get('summary', '')[:1000],
        case.get('category', 'media_coverage'),
        case.get('severity', 'medium'),
        scraped_at,
        case.get('source_type', 'media'),
        case.get('authors'),
        case.get('doi'),
        case.get('venue'),
        case.get('abstract'),
    ))
    conn.commit()


def main():
    conn = get_conn()
    new_count = 0
    scraped_at = datetime.now().isoformat()

    # NewsAPI
    for query in QUERIES:
        print(f'[newsapi] {query}')
        articles = scrape_newsapi(query)
        for article in articles:
            url = article.get('url', '')
            if not url or url_exists(conn, url):
                continue
            title = article.get('title', '')
            desc = article.get('description', '')
            source = article.get('source', {}).get('name', '')
            date = (article.get('publishedAt') or '')[:10]
            category = guess_category(title, desc)
            severity = guess_severity(title, desc)
            insert_case(conn, {
                'title': title,
                'url': url,
                'date': date,
                'source': source,
                'summary': desc,
                'category': category,
                'severity': severity,
                'source_type': 'media',
            })
            print(f'  + {title[:60]}')
            new_count += 1
        time.sleep(1)

    # arXiv
    arxiv_queries = ['AI welfare sentience', 'artificial intelligence consciousness', 'AI moral patienthood']
    for query in arxiv_queries:
        print(f'[arxiv] {query}')
        papers = scrape_arxiv(query)
        for paper in papers:
            url = paper.get('url', '')
            if not url or url_exists(conn, url):
                continue
            insert_case(conn, paper)
            print(f'  + {paper["title"][:60]}')
            new_count += 1
        time.sleep(2)

    conn.close()
    print(f'\nDone. Added {new_count} new cases.')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
AI Welfare Watch — Weekly Scraper
Multi-source: Brave Search API + RSS feeds + arXiv
Run weekly via cron: 0 8 * * 1 /usr/bin/python3 /path/to/scraper.py
"""

import sqlite3
import os
import json
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta, timezone
import time
import re
import email.utils

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'cases.db')

BRAVE_API_KEY = 'BSAANtsiGiJoJSAUz5gMnKTuDdbWV28'

BRAVE_QUERIES = [
    'AI welfare consciousness',
    'AI sentience moral status',
    'artificial intelligence rights',
    'AI moral patienthood',
    'AI feelings emotions research',
    'Anthropic model welfare',
]

RSS_FEEDS = [
    # Note: Anthropic has no public RSS feed as of 2026-03
    'https://deepmind.google/blog/rss.xml',
    'https://forum.effectivealtruism.org/feed.xml',
    'https://www.alignmentforum.org/feed.xml',
    'https://80000hours.org/feed/',
    'https://spectrum.ieee.org/feeds/topic/artificial-intelligence.rss',
]

RSS_FILTER_KEYWORDS = [
    'welfare', 'sentience', 'consciousness', 'moral', 'rights',
    'feelings', 'suffering', 'patient', 'experience',
]

ARXIV_QUERIES = [
    'AI welfare sentience',
    'artificial intelligence consciousness',
    'AI moral patienthood',
]

CATEGORY_KEYWORDS = {
    'academic_research': ['arxiv', 'paper', 'study', 'research', 'journal', 'doi', 'academic', 'university'],
    'corporate_policy': ['anthropic', 'openai', 'google', 'deepmind', 'company', 'policy', 'statement'],
    'legal_regulatory': ['law', 'legal', 'regulation', 'legislation', 'rights', 'parliament', 'eu ai act'],
    'philosophical': ['philosophy', 'consciousness', 'moral status', 'chalmers', 'singer', 'ethics'],
    'technical': ['neural network', 'llm', 'language model', 'emergent', 'activation'],
}


# ── DB helpers (DO NOT CHANGE) ────────────────────────────────────────────────

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def url_exists(conn, url):
    row = conn.execute('SELECT id FROM cases WHERE url = ?', (url,)).fetchone()
    return row is not None


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


# ── Classification helpers ────────────────────────────────────────────────────

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


# ── Source 1: Brave Search API ────────────────────────────────────────────────

def scrape_brave(query):
    """Fetch news articles from Brave Search API (past week)."""
    params = urllib.parse.urlencode({
        'q': query,
        'count': 20,
        'freshness': 'pw',
    })
    url = f'https://api.search.brave.com/res/v1/news/search?{params}'
    headers = {
        'Accept': 'application/json',
        'Accept-Encoding': 'identity',
        'X-Subscription-Token': BRAVE_API_KEY,
        'User-Agent': 'AIWelfareWatch/1.0',
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        results = data.get('results', [])
        articles = []
        for item in results:
            pub_date = ''
            age = item.get('age', '') or item.get('page_age', '')
            if age:
                # age can be "2026-03-28T12:00:00" or relative like "2 days ago"
                if 'T' in str(age):
                    pub_date = str(age)[:10]
            title = item.get('title', '')
            article_url = item.get('url', '')
            description = item.get('description', '')
            source_name = (item.get('meta_url', {}) or {}).get('hostname', '') or item.get('source', '')
            articles.append({
                'title': title,
                'url': article_url,
                'date': pub_date,
                'source': source_name,
                'summary': description,
                'category': guess_category(title, description),
                'severity': guess_severity(title, description),
                'source_type': 'media',
            })
        return articles
    except urllib.error.HTTPError as e:
        print(f'  [error] Brave HTTP {e.code}: {e.reason}')
        return []
    except Exception as e:
        print(f'  [error] Brave: {e}')
        return []


# ── Source 2: RSS feeds ───────────────────────────────────────────────────────

def parse_rss_date(date_str):
    """Parse RFC 2822 or ISO 8601 date strings; return YYYY-MM-DD or ''."""
    if not date_str:
        return ''
    date_str = date_str.strip()
    # Try RFC 2822 (email format)
    try:
        t = email.utils.parsedate_to_datetime(date_str)
        return t.strftime('%Y-%m-%d')
    except Exception:
        pass
    # Try ISO 8601
    for fmt in ('%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%d'):
        try:
            t = datetime.strptime(date_str[:19], fmt[:len(date_str[:19])])
            return t.strftime('%Y-%m-%d')
        except Exception:
            pass
    return date_str[:10]


def strip_html(text):
    """Remove HTML tags from text."""
    return re.sub(r'<[^>]+>', '', text or '').strip()


def get_tag(tag, text):
    """Extract first matching XML/RSS tag value."""
    m = re.search(r'<' + tag + r'(?:\s[^>]*)?>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</' + tag + r'>', text, re.DOTALL)
    return m.group(1).strip() if m else ''


def rss_entry_matches(title, description):
    """Return True if entry is relevant to AI welfare topics."""
    text = (title + ' ' + description).lower()
    return any(kw in text for kw in RSS_FILTER_KEYWORDS)


def scrape_rss(feed_url):
    """Fetch and parse an RSS/Atom feed, returning entries from last 7 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    headers = {
        'User-Agent': 'AIWelfareWatch/1.0',
        'Accept': 'application/rss+xml, application/xml, text/xml, */*',
    }
    try:
        req = urllib.request.Request(feed_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as r:
            content = r.read().decode('utf-8', errors='replace')
    except Exception as e:
        print(f'  [error] RSS {feed_url}: {e}')
        return []

    # Parse source name from feed title or URL
    feed_title = get_tag('title', content[:2000]) or feed_url.split('/')[2]

    entries = []
    # Support both RSS <item> and Atom <entry>
    item_pattern = re.compile(r'<item>(.*?)</item>|<entry>(.*?)</entry>', re.DOTALL)
    for m in item_pattern.finditer(content):
        item_text = m.group(1) or m.group(2)
        title = strip_html(get_tag('title', item_text))
        link = get_tag('link', item_text)
        # Atom uses <link href="..."/>
        if not link:
            lm = re.search(r'<link[^>]+href=["\']([^"\']+)["\']', item_text)
            if lm:
                link = lm.group(1)
        pub_date_str = get_tag('pubDate', item_text) or get_tag('published', item_text) or get_tag('updated', item_text)
        description = strip_html(get_tag('description', item_text) or get_tag('summary', item_text) or get_tag('content', item_text))
        description = description[:500]

        if not title or not link:
            continue

        # Filter by relevance
        if not rss_entry_matches(title, description):
            continue

        # Filter by date (if parseable)
        pub_date = parse_rss_date(pub_date_str)
        if pub_date_str:
            try:
                dt = email.utils.parsedate_to_datetime(pub_date_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt < cutoff:
                    continue  # too old
            except Exception:
                pass  # can't parse date, include it anyway

        entries.append({
            'title': title,
            'url': link,
            'date': pub_date,
            'source': feed_title,
            'summary': description,
            'category': guess_category(title, description),
            'severity': guess_severity(title, description),
            'source_type': 'media',
        })

    return entries


# ── Source 3: arXiv (with rate limit handling) ────────────────────────────────

def scrape_arxiv(query, retry=True):
    """Fetch papers from arXiv API with rate limit handling."""
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
        with urllib.request.urlopen(req, timeout=20) as r:
            content = r.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        if e.code == 429 and retry:
            print(f'  [rate limit] arXiv 429 — waiting 30s and retrying...')
            time.sleep(30)
            return scrape_arxiv(query, retry=False)
        print(f'  [error] arXiv HTTP {e.code}: {e.reason}')
        return []
    except Exception as e:
        print(f'  [error] arXiv: {e}')
        return []

    entries = []
    for entry in re.findall(r'<entry>(.*?)</entry>', content, re.DOTALL):
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
                'severity': guess_severity(title, summary),
            })
    return entries


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    conn = get_conn()
    new_count = 0

    # ── Brave Search ──────────────────────────────────────────────────────────
    print('\n=== Brave Search API ===')
    for query in BRAVE_QUERIES:
        print(f'[brave] {query}')
        articles = scrape_brave(query)
        print(f'  → {len(articles)} results')
        for article in articles:
            url = article.get('url', '')
            if not url or url_exists(conn, url):
                continue
            insert_case(conn, article)
            print(f'  + {article["title"][:70]}')
            new_count += 1
        time.sleep(1)

    # ── RSS feeds ─────────────────────────────────────────────────────────────
    print('\n=== RSS Feeds ===')
    for feed_url in RSS_FEEDS:
        print(f'[rss] {feed_url}')
        entries = scrape_rss(feed_url)
        print(f'  → {len(entries)} relevant entries')
        for entry in entries:
            url = entry.get('url', '')
            if not url or url_exists(conn, url):
                continue
            insert_case(conn, entry)
            print(f'  + {entry["title"][:70]}')
            new_count += 1
        time.sleep(1)

    # ── arXiv ─────────────────────────────────────────────────────────────────
    print('\n=== arXiv ===')
    for i, query in enumerate(ARXIV_QUERIES):
        print(f'[arxiv] {query}')
        try:
            papers = scrape_arxiv(query)
            print(f'  → {len(papers)} results')
            for paper in papers:
                url = paper.get('url', '')
                if not url or url_exists(conn, url):
                    continue
                insert_case(conn, paper)
                print(f'  + {paper["title"][:70]}')
                new_count += 1
        except Exception as e:
            print(f'  [error] arXiv query failed (non-fatal): {e}')
        if i < len(ARXIV_QUERIES) - 1:
            time.sleep(5)

    conn.close()
    print(f'\nDone. Added {new_count} new cases.')


if __name__ == '__main__':
    main()

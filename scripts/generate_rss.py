#!/usr/bin/env python3
"""
AI Welfare Watch — RSS Feed Generator
Generates public/feed.xml from 20 most recent media cases.
"""

import sqlite3
import os
from datetime import datetime
from xml.sax.saxutils import escape

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'cases.db')
OUT_PATH = os.path.join(os.path.dirname(__file__), '..', 'public', 'feed.xml')

SITE_URL = 'https://aiwelfare.watch'
SITE_TITLE = 'AI Welfare Watch'
SITE_DESC = 'Tracking the global conversation on AI sentience, consciousness, and moral consideration.'


def format_rfc2822(date_str):
    try:
        d = datetime.strptime(date_str, '%Y-%m-%d')
        return d.strftime('%a, %d %b %Y 00:00:00 +0000')
    except Exception:
        return datetime.now().strftime('%a, %d %b %Y 00:00:00 +0000')


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute('''
        SELECT * FROM cases
        WHERE source_type != 'academic'
        ORDER BY date DESC
        LIMIT 20
    ''').fetchall()
    conn.close()

    items = []
    for row in rows:
        title = escape(row['title'] or '')
        link = escape(row['url'] or f'{SITE_URL}/#case-{row["id"]}')
        desc = escape(row['summary'] or '')
        pub_date = format_rfc2822(row['date'] or '')
        source = escape(row['source'] or '')
        category = escape(row['category'] or '')
        item = f'''    <item>
      <title>{title}</title>
      <link>{link}</link>
      <description>{desc}</description>
      <pubDate>{pub_date}</pubDate>
      <source url="{SITE_URL}">{SITE_TITLE}</source>
      <category>{category}</category>
      <guid isPermaLink="true">{link}</guid>
    </item>'''
        items.append(item)

    build_date = datetime.now().strftime('%a, %d %b %Y %H:%M:%S +0000')
    feed = f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{SITE_TITLE}</title>
    <link>{SITE_URL}</link>
    <description>{SITE_DESC}</description>
    <language>en-us</language>
    <lastBuildDate>{build_date}</lastBuildDate>
    <atom:link href="{SITE_URL}/feed.xml" rel="self" type="application/rss+xml"/>
{chr(10).join(items)}
  </channel>
</rss>
'''

    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        f.write(feed)
    print(f'Generated {OUT_PATH} with {len(items)} items.')


if __name__ == '__main__':
    main()

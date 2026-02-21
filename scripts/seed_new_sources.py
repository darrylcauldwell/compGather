#!/usr/bin/env python3
"""Seed script to register new equestrian sources via the compGather API.

Usage:
    python scripts/seed_new_sources.py [--base-url http://localhost:8001]

Each source uses parser_key=null (generic LLM fallback).
Skips sources that already exist (matched by URL).
"""

import argparse
import sys

import httpx

NEW_SOURCES = [
    {
        "name": "British Eventing",
        "url": "https://www.britisheventing.com/calendar",
        "parser_key": None,
    },
    {
        "name": "British Dressage",
        "url": "https://www.britishdressage.co.uk/competitions/",
        "parser_key": None,
    },
    {
        "name": "British Riding Clubs (BRC)",
        "url": "https://www.brc.org.uk/competitions/",
        "parser_key": None,
    },
    {
        "name": "EquoEvents",
        "url": "https://www.equoevents.co.uk/",
        "parser_key": None,
    },
    {
        "name": "EquiLive",
        "url": "https://www.equi-live.com/",
        "parser_key": None,
    },
    {
        "name": "My Riding Life",
        "url": "https://www.myridinglife.com/",
        "parser_key": None,
    },
]


def main():
    parser = argparse.ArgumentParser(description="Seed new equestrian sources")
    parser.add_argument("--base-url", default="http://localhost:8001", help="compGather API base URL")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    api_url = f"{base}/api/sources"

    # Get existing sources to avoid duplicates
    resp = httpx.get(api_url, timeout=10)
    resp.raise_for_status()
    existing_urls = {s["url"] for s in resp.json()}

    created = 0
    skipped = 0
    for source in NEW_SOURCES:
        if source["url"] in existing_urls:
            print(f"  SKIP  {source['name']} — already exists")
            skipped += 1
            continue

        resp = httpx.post(api_url, json=source, timeout=10)
        if resp.status_code == 201:
            print(f"  ADD   {source['name']} (id={resp.json()['id']})")
            created += 1
        else:
            print(f"  FAIL  {source['name']} — {resp.status_code}: {resp.text}", file=sys.stderr)

    print(f"\nDone: {created} created, {skipped} skipped")


if __name__ == "__main__":
    main()

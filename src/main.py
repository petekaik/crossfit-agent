#!/usr/bin/env python3
"""
CrossFit Competition Tracker - Main Entry Point

Käynnistää haun ja synkronoinnin.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from scraper import CompetitionAggregator
from calendar_sync import GoogleCalendarSync, setup_credentials


# Default paths
DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

COMPETITIONS_FILE = DATA_DIR / "competitions.json"
STATE_FILE = DATA_DIR / "state.json"


def load_state() -> dict:
    """Load last run state."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    """Save current state."""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def save_competitions(competitions: list, filepath: Path = COMPETITIONS_FILE):
    """Save competitions to JSON file."""
    data = []
    for comp in competitions:
        data.append({
            "name": comp.name,
            "date_start": comp.date_start.isoformat() if comp.date_start else None,
            "date_end": comp.date_end.isoformat() if comp.date_end else None,
            "location": comp.location,
            "country": comp.country,
            "level": comp.level.value,
            "event_type": comp.event_type.value,
            "youtube_url": comp.youtube_url,
            "ticket_url": comp.ticket_url,
            "info_url": comp.info_url,
            "description": comp.description,
            "is_all_day": comp.is_all_day,
            "video_feeds": comp.video_feeds if comp.video_feeds else None,
            "category": comp.category,
            "color_id": comp.color_id,
        })
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"Saved {len(competitions)} competitions to {filepath}")


def run_search():
    """Run competition search."""
    print("=" * 50)
    print("CrossFit Competition Tracker - Search")
    print("=" * 50)
    print(f"Started at: {datetime.now().isoformat()}")
    print()
    
    aggregator = CompetitionAggregator()
    competitions = aggregator.fetch_all()
    
    print(f"\nFound {len(competitions)} competitions")
    
    # Classify and display
    elite = [c for c in competitions if c.level.value == "elite"]
    hobby = [c for c in competitions if c.level.value == "hobby"]
    
    print(f"  - Elite: {len(elite)}")
    print(f"  - Hobby: {len(hobby)}")
    
    # Save to file
    save_competitions(competitions)
    
    # Update state
    state = load_state()
    state['last_search'] = datetime.now().isoformat()
    state['competitions_found'] = len(competitions)
    save_state(state)
    
    return competitions


def run_sync(dry_run: bool = False, console_auth: bool = False):
    """Sync competitions to Google Calendar.
    
    Uses Service Account if env vars are set, otherwise OAuth.
    credential.json is only checked for OAuth fallback.
    """
    print("=" * 50)
    print("CrossFit Competition Tracker - Calendar Sync")
    print("=" * 50)
    print(f"Started at: {datetime.now().isoformat()}")
    print()
    
    sa_configured = bool(os.environ.get('SA_EMAIL'))
    
    # credential.json only needed for OAuth fallback
    if not sa_configured:
        creds_path = Path("credentials.json")
        if not creds_path.exists():
            setup_credentials()
            return False
    
    # Load competitions
    if not COMPETITIONS_FILE.exists():
        print(f"Error: No competitions file found at {COMPETITIONS_FILE}")
        print("Run search first: python main.py search")
        return False
    
    with open(COMPETITIONS_FILE) as f:
        data = json.load(f)
    
    print(f"Loaded {len(data)} competitions from file")
    
    if dry_run:
        print("\n[DRY RUN] Would sync the following events:")
        for item in data:
            print(f"  - {item['name']} ({item['level']})")
        return True
    
    # Authenticate and sync
    sync = GoogleCalendarSync()
    if not sync.authenticate(console_mode=console_auth):
        print("Authentication failed")
        return False
    
    # Convert dicts back to Competition objects
    from scraper import Competition, CompetitionLevel, EventType
    competitions = []
    for item in data:
        comp = Competition(
            name=item['name'],
            date_start=datetime.fromisoformat(item['date_start']) if item['date_start'] else None,
            date_end=datetime.fromisoformat(item['date_end']) if item['date_end'] else None,
            location=item['location'],
            country=item['country'],
            level=CompetitionLevel(item['level']),
            event_type=EventType(item.get('event_type', 'independent_elite')),
            youtube_url=item.get('youtube_url'),
            ticket_url=item.get('ticket_url'),
            info_url=item.get('info_url'),
            description=item.get('description', ''),
            is_all_day=item.get('is_all_day', False),
            video_feeds=item.get('video_feeds'),
            category=item.get('category', ''),
            color_id=item.get('color_id', ''),
        )
        competitions.append(comp)
    
    results = sync.sync_competitions(competitions)
    
    print(f"\nSync results:")
    print(f"  - Created: {results['created']}")
    print(f"  - Updated: {results['updated']}")
    print(f"  - Skipped: {results['skipped']}")
    print(f"  - Failed: {results['failed']}")
    
    # Update state
    state = load_state()
    state['last_sync'] = datetime.now().isoformat()
    state['sync_results'] = results
    save_state(state)
    
    return True


def run_full():
    """Run full pipeline: search + sync."""
    print("=" * 50)
    print("CrossFit Competition Tracker - Full Run")
    print("=" * 50)
    print()
    
    competitions = run_search()
    print()
    
    if competitions:
        run_sync()
    else:
        print("No competitions found, skipping sync")
    
    print()
    print("=" * 50)
    print("Full run completed!")
    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(
        description="CrossFit Competition Tracker"
    )
    parser.add_argument(
        'command',
        choices=['search', 'sync', 'full', 'setup'],
        help='Command to run: search (find competitions), sync (update calendar), full (both), setup (configure)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    parser.add_argument(
        '--console-auth',
        action='store_true',
        help='Use console-based authentication (copy-paste URL) instead of browser'
    )
    
    args = parser.parse_args()
    
    if args.command == 'search':
        run_search()
    elif args.command == 'sync':
        run_sync(dry_run=args.dry_run, console_auth=args.console_auth)
    elif args.command == 'full':
        run_full()
    elif args.command == 'setup':
        setup_credentials()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

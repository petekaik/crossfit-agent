#!/usr/bin/env python3
"""Delete duplicate events from Urheilutapahtumat calendar.

Keeps the most recently created event for each (summary, start_date).
Deletes all older duplicates.
"""
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from calendar_sync import GoogleCalendarSync

DRY_RUN = False  # Set False to actually delete

def main():
    sync = GoogleCalendarSync()
    if not sync.authenticate():
        print("AUTH FAILED")
        sys.exit(1)

    print(f"Calendar ID: {sync.calendar_id}")
    print(f"Mode: {'DRY RUN (no deletions)' if DRY_RUN else 'LIVE (will delete!)'}\n")

    # Fetch all events
    time_min = "2025-01-01T00:00:00Z"
    time_max = "2027-12-31T00:00:00Z"
    page_token = None
    all_events = []

    while True:
        result = sync.service.events().list(
            calendarId=sync.calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            pageToken=page_token,
            maxResults=2500,
            orderBy='startTime'
        ).execute()
        events = result.get('items', [])
        all_events.extend(events)
        page_token = result.get('nextPageToken')
        if not page_token:
            break

    print(f"Total events in calendar: {len(all_events)}")

    # Group by (summary, start_date) to find duplicates
    groups = defaultdict(list)
    for ev in all_events:
        summary = ev.get('summary', '')
        start = ev.get('start', {}).get('dateTime', ev.get('start', {}).get('date', ''))
        created = ev.get('created', '')
        key = (summary, start[:10])  # (name, date only — ignore time)
        groups[key].append({
            'id': ev['id'],
            'summary': summary,
            'start': start,
            'created': created,
        })

    to_delete = []
    kept = []

    for key, evts in groups.items():
        # Sort by created time, newest first
        evts.sort(key=lambda e: e['created'], reverse=True)
        kept.append(evts[0])  # Keep newest
        if len(evts) > 1:
            to_delete.extend(evts[1:])  # Delete older

    print(f"Distinct events to keep: {len(kept)}")
    print(f"Duplicates to delete:    {len(to_delete)}")

    if not to_delete:
        print("\n✅ No duplicates found!")
        return

    print(f"\nDuplicates to delete:")
    for ev in to_delete:
        print(f"  🗑  {ev['summary']}  (start={ev['start']}, created={ev['created']}, id={ev['id'][-12:]})")

    if DRY_RUN:
        print(f"\n⚠️  DRY RUN — no events were deleted. Run with DRY_RUN=False to execute.")
        return

    # Actually delete
    deleted = 0
    failed = 0
    for ev in to_delete:
        try:
            sync.service.events().delete(
                calendarId=sync.calendar_id,
                eventId=ev['id']
            ).execute()
            deleted += 1
            print(f"  ✓ Deleted: {ev['summary'][:60]}")
        except Exception as e:
            failed += 1
            print(f"  ✗ Failed: {ev['summary'][:60]} — {e}")

    print(f"\n{'='*50}")
    print(f"Deleted: {deleted}")
    print(f"Failed:  {failed}")
    print(f"Remaining events: {len(kept)}")

if __name__ == "__main__":
    main()

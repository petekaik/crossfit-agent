#!/usr/bin/env python3
"""Diagnose duplicate events in Urheilutapahtumat calendar."""
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from calendar_sync import GoogleCalendarSync

sync = GoogleCalendarSync()
if not sync.authenticate():
    print("AUTH FAILED")
    sys.exit(1)

print(f"Calendar ID: {sync.calendar_id}\n")

# Fetch ALL events from Jan 2025 to end of 2027
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

# Group by event summary (name)
by_name = defaultdict(list)
for ev in all_events:
    summary = ev.get('summary', 'NO SUMMARY')
    start = ev.get('start', {}).get('dateTime', ev.get('start', {}).get('date', '?'))
    by_name[summary].append({
        'id': ev['id'],
        'start': start,
        'created': ev.get('created', '?'),
    })

# Show duplicates
total_dup_events = 0
total_dup_groups = 0
unique_count = 0

for name, evts in sorted(by_name.items()):
    if len(evts) > 1:
        total_dup_groups += 1
        total_dup_events += len(evts) - 1  # events beyond first
        print(f"\n❌ DUPLICATE x{len(evts)}: {name}")
        for e in evts:
            print(f"     ID={e['id'][-12:]}... start={e['start']} created={e['created']}")
    else:
        unique_count += 1

print(f"\n{'='*60}")
print(f"Unique event names: {unique_count}")
print(f"Duplicate groups:   {total_dup_groups}")
print(f"Excess duplicates:   {total_dup_events} (events to delete)")
print(f"Distinct would be:   {len(all_events) - total_dup_events}")

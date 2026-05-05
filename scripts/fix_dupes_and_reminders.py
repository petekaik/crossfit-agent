"""Fix: 1) Delete dup WFP Tour Stop 1, 2) Remove all email reminders."""
import sys
sys.path.insert(0, "src")
from calendar_sync import GoogleCalendarSync

sync = GoogleCalendarSync()
sync.authenticate()

# ── Step 1: Find and delete the WFP Tour Stop 1 duplicate ──
time_min = "2026-05-01T00:00:00Z"
time_max = "2026-05-02T00:00:00Z"

result = sync.service.events().list(
    calendarId=sync.calendar_id,
    timeMin=time_min,
    timeMax=time_max,
    singleEvents=True
).execute()

wfp_events = []
for ev in result.get('items', []):
    s = ev.get('summary', '')
    if 'WFP' in s and 'Tour Stop 1' in s:
        wfp_events.append({'id': ev['id'], 'summary': s, 'created': ev.get('created', '')})

print(f"WFP Tour Stop 1 events found: {len(wfp_events)}")
for e in wfp_events:
    print(f"  {e['summary']} (created={e['created']}, id={e['id'][-12:]})")

if len(wfp_events) > 1:
    # Delete the older one (keep the one with em-dash from new scraper)
    wfp_events.sort(key=lambda e: e['created'], reverse=True)
    keep = wfp_events[0]
    for e in wfp_events[1:]:
        print(f"\nDeleting duplicate: {e['summary']}")
        sync.service.events().delete(
            calendarId=sync.calendar_id,
            eventId=e['id']
        ).execute()
        print(f"  ✓ Deleted")
    print(f"\nKeeping: {keep['summary']}")
else:
    print("No duplicates found")

# ── Step 2: Remove email reminders from ALL events ──
print(f"\n{'='*50}")
print("Removing email reminders from all events...")

time_min = "2025-01-01T00:00:00Z"
time_max = "2027-12-31T00:00:00Z"
page_token = None
fixed = 0

while True:
    result = sync.service.events().list(
        calendarId=sync.calendar_id,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        pageToken=page_token,
        maxResults=2500,
    ).execute()

    for ev in result.get('items', []):
        reminders = ev.get('reminders', {})
        old_overrides = reminders.get('overrides', [])

        # Filter out email reminders
        new_overrides = [r for r in old_overrides if r.get('method') != 'email']

        if len(new_overrides) != len(old_overrides):
            # Update the event
            update = {
                'reminders': {
                    'useDefault': False,
                    'overrides': new_overrides,
                }
            }
            sync.service.events().patch(
                calendarId=sync.calendar_id,
                eventId=ev['id'],
                body=update
            ).execute()
            fixed += 1

    page_token = result.get('nextPageToken')
    if not page_token:
        break

print(f"Events fixed (email reminders removed): {fixed}")

# ── Step 3: Final count ──
result = sync.service.events().list(
    calendarId=sync.calendar_id,
    timeMin=time_min,
    timeMax=time_max,
    singleEvents=True,
    maxResults=2500,
).execute()
total = len(result.get('items', []))
print(f"\nTotal events in calendar: {total}")
print("Done ✓")

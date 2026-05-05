"""Check WFP/London events and all email reminders in calendar."""
import sys
sys.path.insert(0, "src")
from calendar_sync import GoogleCalendarSync

sync = GoogleCalendarSync()
sync.authenticate()

time_min = "2025-01-01T00:00:00Z"
time_max = "2027-12-31T00:00:00Z"
events = []
page_token = None

while True:
    r = sync.service.events().list(
        calendarId=sync.calendar_id,
        timeMin=time_min, timeMax=time_max,
        singleEvents=True, pageToken=page_token,
        maxResults=2500).execute()
    events.extend(r.get('items', []))
    page_token = r.get('nextPageToken')
    if not page_token:
        break

print(f"Total events: {len(events)}\n")

# Find WFP/London/Tour Stop events
print("=== WFP / London / Tour Stop events ===")
for ev in events:
    s = ev.get('summary', '')
    if any(kw in s for kw in ['WFP', 'Tour Stop', 'London', 'World Fitness']):
        start = ev.get('start', {}).get('dateTime', ev.get('start', {}).get('date', ''))
        reminders = ev.get('reminders', {})
        print(f"  {s}")
        print(f"    ID={ev['id'][-16:]}, start={start[:10]}, reminders={reminders}")

# Check all events with email reminders
print("\n=== Events with email reminders ===")
email_count = 0
for ev in events:
    reminders = ev.get('reminders', {})
    overrides = reminders.get('overrides', [])
    for r in overrides:
        if r.get('method') == 'email':
            email_count += 1
            print(f"  Email reminder: {ev.get('summary')} (id={ev['id'][-12:]})")
            break

print(f"\nTotal events with email reminders: {email_count}")

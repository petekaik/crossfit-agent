"""
Google Calendar Sync Module

Synkronoi crossfit-kisat Google Kalenteriin.
"""

import os
import re
from datetime import datetime, timedelta
from typing import List, Optional
from dataclasses import dataclass
from urllib.parse import urlparse, parse_qs

# Google API
import json
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from scraper import Competition, CompetitionLevel


# Google Calendar API scopes
SCOPES = ['https://www.googleapis.com/auth/calendar']

# Timezone for all events
DEFAULT_TIMEZONE = 'Europe/Helsinki'  # EET/EEST


@dataclass
class CalendarEvent:
    """Represents a calendar event."""
    summary: str
    description: str
    start: datetime
    end: datetime
    location: str
    timezone: str = DEFAULT_TIMEZONE
    source_url: Optional[str] = None
    is_all_day: bool = False


class GoogleCalendarSync:
    """Syncs competitions to Google Calendar.
    
    Authentication priority:
    1. Service Account (SA) — if SA_EMAIL + SA_PRIVATE_KEY_ID env vars are set
       Uses private.pem for signing. No refresh-token expiry. Best for cron.
    2. OAuth (InstalledApp) — fallback for interactive/local development.
    """
    
    CALENDAR_NAME = 'Urheilutapahtumat'
    
    # Service Account defaults (override via env vars)
    SA_SCOPES = ['https://www.googleapis.com/auth/calendar']
    SA_TOKEN_URI = 'https://oauth2.googleapis.com/token'
    
    def __init__(self, credentials_path: str = "credentials.json", token_path: str = "token.json"):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = None
        self.calendar_id = None  # Will be set to Urheilutapahtumat calendar
        self._event_cache = {}   # (summary, date) -> event_id, built before sync
        
    def get_or_create_calendar(self) -> str:
        """Get or create 'Urheilutapahtumat' calendar.
        
        SA-authenticated: tries CALENDAR_ID env var first (shared calendars
        don't always appear in calendarList), then checks calendarList.
        OAuth-authenticated: lists all calendars by summary name.
        """
        if not self.service:
            raise ValueError("Not authenticated")
        
        # Check CALENDAR_ID env var first (needed for SA with shared calendars)
        env_cal_id = os.environ.get('CALENDAR_ID')
        if env_cal_id:
            try:
                # Verify the calendar is accessible
                self.service.events().list(
                    calendarId=env_cal_id, maxResults=1
                ).execute()
                print(f"Using calendar from CALENDAR_ID: {self.CALENDAR_NAME}")
                return env_cal_id
            except Exception:
                print(f"CALENDAR_ID is set but not accessible, falling back to calendar list")
        
        # List all calendars
        calendars_result = self.service.calendarList().list().execute()
        calendars = calendars_result.get('items', [])
        
        # Find existing calendar
        for cal in calendars:
            if cal.get('summary') == self.CALENDAR_NAME:
                print(f"Using existing calendar: {self.CALENDAR_NAME}")
                return cal['id']
        
        # If SA and shared calendar not in list, try to add it
        if not calendars and os.environ.get('SA_EMAIL') and env_cal_id:
            try:
                self.service.calendarList().insert(
                    body={'id': env_cal_id, 'selected': True, 'hidden': False}
                ).execute()
                print(f"Added shared calendar: {self.CALENDAR_NAME}")
                return env_cal_id
            except Exception as e:
                print(f"Could not add shared calendar to list: {e}")
                # Try using the ID directly anyway
                return env_cal_id
        
        # Create new calendar
        calendar = {
            'summary': self.CALENDAR_NAME,
            'timeZone': DEFAULT_TIMEZONE,
            'description': 'CrossFit-kilpailut ja urheilutapahtumat'
        }
        
        created = self.service.calendars().insert(body=calendar).execute()
        print(f"Created new calendar: {self.CALENDAR_NAME}")
        return created['id']
        
    def set_sports_calendar(self):
        """Set calendar to Urheilutapahtumat."""
        self.calendar_id = self.get_or_create_calendar()
        
    def _authenticate_with_service_account(self) -> bool:
        """Authenticate using Service Account + private key.
        
        Reads SA_EMAIL and SA_PRIVATE_KEY_ID from environment variables.
        Uses private.pem for JWT signing.
        
        Returns:
            True if SA authentication succeeded.
        """
        sa_email = os.environ.get('SA_EMAIL')
        sa_key_id = os.environ.get('SA_PRIVATE_KEY_ID')
        
        if not sa_email:
            return False
        
        # Resolve private.pem location (look in project root and src/)
        key_paths = [
            Path(__file__).parent.parent / 'private.pem',  # ../private.pem
            Path('private.pem'),
        ]
        key_file = None
        for p in key_paths:
            if p.exists():
                key_file = str(p)
                break
        
        if not key_file:
            print(f"SA_EMAIL is set ({sa_email}) but private.pem not found")
            return False
        
        private_key = Path(key_file).read_text()
        
        print(f"Authenticating as Service Account: {sa_email}")
        
        # Build service account info dict
        sa_info = {
            'type': 'service_account',
            'project_id': os.environ.get('SA_PROJECT_ID', ''),
            'private_key_id': sa_key_id or '',
            'private_key': private_key,
            'client_email': sa_email,
            'token_uri': self.SA_TOKEN_URI,
        }
        
        creds = service_account.Credentials.from_service_account_info(
            sa_info, scopes=self.SA_SCOPES
        )
        
        self.service = build('calendar', 'v3', credentials=creds)
        self.set_sports_calendar()
        return True

    def authenticate(self, console_mode: bool = False) -> bool:
        """Authenticate with Google Calendar API.
        
        Tries Service Account first (non-interactive, no token expiry),
        falls back to OAuth (interactive, requires browser/URL copy-paste).
        
        Args:
            console_mode: If True, use console-based auth (copy-paste URL).
                         If False, try to open browser automatically.
                         Only applies to OAuth fallback.
        """
        # Try Service Account first (non-interactive, no token expiry)
        if self._authenticate_with_service_account():
            return True
        
        print("Service Account not configured, falling back to OAuth...")
        
        creds = None
        
        # Load existing token
        if os.path.exists(self.token_path):
            creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
        
        # If no valid credentials, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_path):
                    print(f"Error: {self.credentials_path} not found.")
                    print("Download it from Google Cloud Console:")
                    print("https://console.cloud.google.com/apis/credentials")
                    return False
                    
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES)
                
                if console_mode:
                    # Console-based auth with explicit redirect_uri for Desktop app
                    # Desktop apps use localhost redirect
                    flow.redirect_uri = 'http://localhost'
                    
                    auth_url, _ = flow.authorization_url(
                        access_type='offline',
                        include_granted_scopes='true',
                        prompt='consent'
                    )
                    
                    print("\n" + "=" * 60)
                    print("Google Calendar Authentication")
                    print("=" * 60)
                    print("\n1. Open this URL in your browser:")
                    print(f"\n   {auth_url}\n")
                    print("2. Sign in with Google and authorize")
                    print("3. Browser will redirect to localhost and show 'This site can't be reached'")
                    print("4. Copy the FULL URL from the browser's address bar")
                    print("   (starts with: http://localhost/?code=...)")
                    print("5. Paste the entire URL below:\n")
                    
                    redirect_url = input("Full redirect URL: ").strip()
                    
                    # Extract code from URL
                    from urllib.parse import urlparse, parse_qs
                    parsed = urlparse(redirect_url)
                    params = parse_qs(parsed.query)
                    code = params.get('code', [None])[0]
                    
                    if not code:
                        print("Error: Could not extract code from URL")
                        return False
                    
                    # Exchange code for token
                    flow.fetch_token(code=code)
                    creds = flow.credentials
                else:
                    try:
                        # Try browser-based auth first
                        creds = flow.run_local_server(port=0)
                    except Exception as e:
                        print(f"Browser auth failed: {e}")
                        print("\n⚠️  Please run with --console-auth flag for manual authentication")
            
            # Save token for future runs
            with open(self.token_path, 'w') as token:
                token.write(creds.to_json())
        
        self.service = build('calendar', 'v3', credentials=creds)
        
        # Set up sports calendar
        self.set_sports_calendar()
        
        return True
    
    def set_calendar(self, calendar_id: str):
        """Set target calendar ID."""
        self.calendar_id = calendar_id
    
    def competition_to_event(self, competition: Competition) -> Optional[CalendarEvent]:
        """Convert Competition to CalendarEvent."""
        if not competition.date_start:
            print(f"Skipping {competition.name}: no start date")
            return None
        
        # Build description
        description_parts = [competition.description] if competition.description else []
        
        if competition.info_url:
            description_parts.append(f"\nInfo: {competition.info_url}")
        if competition.ticket_url:
            description_parts.append(f"\nTickets: {competition.ticket_url}")
        
        # Video feeds (supports multiple streams — morning/afternoon/event-specific)
        if competition.video_feeds:
            if len(competition.video_feeds) == 1 and not competition.video_feeds[0].get('label'):
                description_parts.append(f"\nYouTube: {competition.video_feeds[0]['url']}")
            else:
                feeds = "\n".join(
                    f"  {vf.get('label', 'Stream')}: {vf['url']}"
                    for vf in competition.video_feeds
                )
                description_parts.append(f"\nVideofeedit:\n{feeds}")
        elif competition.youtube_url:
            description_parts.append(f"\nYouTube: {competition.youtube_url}")
        
        description_parts.append(f"\nLevel: {competition.level.value}")
        
        if competition.is_all_day:
            description_parts.append("\n(Viitteellinen ajanjakso — ei yksittäinen kisatapahtuma)")
        
        # Calculate end date
        end_date = competition.date_end or (competition.date_start + timedelta(days=1))
        
        return CalendarEvent(
            summary=f"[CrossFit] {competition.name}",
            description="\n".join(description_parts) if description_parts else "",
            start=competition.date_start,
            end=end_date,
            location=f"{competition.location}, {competition.country}",
            source_url=competition.info_url,
            is_all_day=competition.is_all_day,
        )
    
    def create_event(self, event: CalendarEvent) -> Optional[str]:
        """Create a single event in Google Calendar."""
        if not self.service:
            print("Error: Not authenticated")
            return None
        
        event_body = {
            'summary': event.summary,
            'description': event.description,
            'location': event.location,
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 60},
                ],
            },
        }
        
        if event.is_all_day:
            # All-day event: no reminders (season periods are just informational)
            event_body['start'] = {'date': event.start.strftime('%Y-%m-%d')}
            event_body['end'] = {'date': event.end.strftime('%Y-%m-%d')}
            event_body['reminders'] = {'useDefault': False, 'overrides': [
                {'method': 'popup', 'minutes': 0}
            ]}
        else:
            event_body['start'] = {
                'dateTime': event.start.isoformat(),
                'timeZone': event.timezone,
            }
            event_body['end'] = {
                'dateTime': event.end.isoformat(),
                'timeZone': event.timezone,
            }
        
        try:
            result = self.service.events().insert(
                calendarId=self.calendar_id,
                body=event_body
            ).execute()
            print(f"Event created: {result.get('htmlLink')}")
            return result.get('id')
        except HttpError as e:
            print(f"Error creating event: {e}")
            return None

    def update_event(self, event_id: str, event: CalendarEvent) -> bool:
        """Update an existing event in Google Calendar."""
        if not self.service:
            print("Error: Not authenticated")
            return False

        event_body = {
            'summary': event.summary,
            'description': event.description,
            'location': event.location,
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 60},
                ],
            },
        }

        if event.is_all_day:
            event_body['start'] = {'date': event.start.strftime('%Y-%m-%d')}
            event_body['end'] = {'date': event.end.strftime('%Y-%m-%d')}
            event_body['reminders'] = {'useDefault': False, 'overrides': [
                {'method': 'popup', 'minutes': 0}
            ]}
        else:
            event_body['start'] = {
                'dateTime': event.start.isoformat(),
                'timeZone': event.timezone,
            }
            event_body['end'] = {
                'dateTime': event.end.isoformat(),
                'timeZone': event.timezone,
            }

        try:
            self.service.events().update(
                calendarId=self.calendar_id,
                eventId=event_id,
                body=event_body
            ).execute()
            return True
        except HttpError as e:
            print(f"Error updating event: {e}")
            return False
    
    def _build_event_cache(self) -> dict:
        """Build a lookup cache of all existing events: (summary, start_date) -> event_id.
        
        Fetches all events once to avoid per-competition API calls and reduce error surface.
        """
        if not self.service:
            return {}
        
        cache = {}
        time_min = "2025-01-01T00:00:00Z"
        time_max = "2027-12-31T00:00:00Z"
        page_token = None
        
        try:
            while True:
                result = self.service.events().list(
                    calendarId=self.calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    pageToken=page_token,
                    maxResults=2500,
                ).execute()
                
                for ev in result.get('items', []):
                    summary = ev.get('summary', '')
                    # Normalize dashes in cache key for matching
                    summary_norm = re.sub(r'[—–-]', '-', summary)
                    # All-day events use 'date', timed events use 'dateTime'
                    start = ev.get('start', {}).get('dateTime', ev.get('start', {}).get('date', ''))
                    key = (summary_norm, start[:10])  # (name, date)
                    cache[key] = ev['id']
                
                page_token = result.get('nextPageToken')
                if not page_token:
                    break
            
            print(f"Event cache: {len(cache)} existing events loaded")
        except Exception as e:
            print(f"Warning: Failed to build event cache: {e}")
        
        return cache
    
    def find_existing_event(self, competition: Competition) -> Optional[str]:
        """Check if event already exists in calendar with exact match."""
        if not self.service or not competition.date_start:
            return None
        
        expected_summary = f"[CrossFit] {competition.name}"
        start_date = competition.date_start.strftime('%Y-%m-%d')
        
        # Check cache
        key = (expected_summary, start_date)
        if key in self._event_cache:
            return self._event_cache[key]
        
        # Backwards compat: check without prefix
        key_no_prefix = (competition.name, start_date)
        if key_no_prefix in self._event_cache:
            return self._event_cache[key_no_prefix]
        
        # Fallback: search across full competition date range
        if competition.date_end:
            time_min = competition.date_start.replace(hour=0, minute=0, second=0).isoformat() + 'Z'
            time_max = (competition.date_end + timedelta(days=1)).replace(hour=0, minute=0, second=0).isoformat() + 'Z'
        else:
            time_min = competition.date_start.replace(hour=0, minute=0, second=0).isoformat() + 'Z'
            time_max = (competition.date_start + timedelta(days=1)).replace(hour=0, minute=0, second=0).isoformat() + 'Z'
        
        try:
            events_result = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True
            ).execute()
            
            events = events_result.get('items', [])
            
            for event in events:
                if event.get('summary') == expected_summary:
                    return event['id']
                if event.get('summary') == competition.name:
                    return event['id']
                    
        except Exception as e:
            print(f"Warning: Error searching events for {competition.name}: {e}")
            # Don't return None silently — log and fall through
            # Returning None here would cause a duplicate creation
        
        return None
    
    def sync_competition(self, competition: Competition, update_existing: bool = True) -> bool:
        """Sync a single competition to calendar."""
        event = self.competition_to_event(competition)
        if not event:
            return False
        
        # Check for existing event
        existing_id = self.find_existing_event(competition)
        
        if existing_id and update_existing:
            # Update existing event
            print(f"Updating existing event for {competition.name}")
            # TODO: Implement update logic
            return True
        elif existing_id:
            print(f"Event already exists for {competition.name}, skipping")
            return True
        else:
            # Create new event
            event_id = self.create_event(event)
            return event_id is not None
    
    def _deduplicate_competitions(self, competitions: List[Competition]) -> List[Competition]:
        """Remove duplicate competitions based on name and date."""
        seen = {}
        unique = []
        
        for comp in competitions:
            # Create unique key from name + date
            if comp.date_start:
                key = f"{comp.name.lower().strip()}_{comp.date_start.strftime('%Y-%m-%d')}"
            else:
                key = comp.name.lower().strip()
            
            if key not in seen:
                seen[key] = comp
                unique.append(comp)
            else:
                print(f"Skipping duplicate: {comp.name}")
        
        return unique
    
    def sync_competitions(self, competitions: List[Competition], update_existing: bool = True) -> dict:
        """Sync multiple competitions to calendar."""
        results = {
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'failed': 0
        }
        
        # Deduplicate before syncing
        unique_competitions = self._deduplicate_competitions(competitions)
        print(f"Deduplicated: {len(competitions)} -> {len(unique_competitions)} competitions")
        
        # Build event cache once to prevent duplicate creation
        self._event_cache = self._build_event_cache()
        
        for comp in unique_competitions:
            if not comp.date_start:
                results['skipped'] += 1
                continue
            
            # Check for existing event
            existing_id = self.find_existing_event(comp)
            
            if existing_id:
                if update_existing:
                    event = self.competition_to_event(comp)
                    if event and self.update_event(existing_id, event):
                        results['updated'] += 1
                    else:
                        results['failed'] += 1
                else:
                    results['skipped'] += 1
                continue
            
            # Create new event
            event = self.competition_to_event(comp)
            if event:
                event_id = self.create_event(event)
                if event_id:
                    results['created'] += 1
                else:
                    results['failed'] += 1
            else:
                results['failed'] += 1
        
        return results


def setup_credentials():
    """Guide user through Google Calendar API setup."""
    print("""
=== Google Calendar API Setup ===

1. Go to https://console.cloud.google.com/
2. Create a new project (or select existing)
3. Enable Google Calendar API:
   - APIs & Services > Library
   - Search "Google Calendar API"
   - Click "Enable"

4. Create OAuth credentials:
   - APIs & Services > Credentials
   - Click "Create Credentials" > "OAuth client ID"
   - Application type: "Desktop app"
   - Name: "CrossFit Tracker"
   - Click "Create"

5. Download the JSON file and save as 'credentials.json'
   in this directory

6. Run the script again - it will open a browser for authentication

For more details: https://developers.google.com/calendar/api/quickstart/python
""")


if __name__ == "__main__":
    # Check if credentials exist
    if not os.path.exists("credentials.json"):
        setup_credentials()
        exit(1)
    
    # Test authentication
    sync = GoogleCalendarSync()
    if sync.authenticate():
        print("Successfully authenticated with Google Calendar!")
        
        # Test: List upcoming events
        print("\nUpcoming events in primary calendar:")
        now = datetime.utcnow().isoformat() + 'Z'
        events_result = sync.service.events().list(
            calendarId='primary', timeMin=now,
            maxResults=10, singleEvents=True,
            orderBy='startTime').execute()
        events = events_result.get('items', [])
        
        if not events:
            print('No upcoming events found.')
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            print(f"  {start}: {event['summary']}")
    else:
        print("Authentication failed")

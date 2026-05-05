"""
Reppi.fi scraper - Suomen crossfit-kisojen tietojen haku
Parannettu versio: Playwright + API + virheenkäsittely + fallback
"""

import json
import re
import time
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

import requests
from bs4 import BeautifulSoup

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CompetitionLevel(Enum):
    HOBBY = "hobby"
    ELITE = "elite"
    UNKNOWN = "unknown"


@dataclass
class Competition:
    """Represents a competition."""
    name: str
    date_start: Optional[datetime]
    date_end: Optional[datetime]
    location: str
    country: str
    level: CompetitionLevel
    youtube_url: Optional[str] = None
    ticket_url: Optional[str] = None
    info_url: Optional[str] = None
    description: str = ""
    registration_end: Optional[datetime] = None
    price: Optional[str] = None
    categories: List[str] = None
    
    def __post_init__(self):
        if self.categories is None:
            self.categories = []


class ReppiScraper:
    """
    Scraper for reppi.fi - Finnish CrossFit competition platform.
    
    Strategy:
    1. Try API endpoints first (fastest, most reliable)
    2. Fall back to Playwright for JavaScript-rendered content
    3. Final fallback to hardcoded known competitions
    """
    
    BASE_URL = "https://reppi.fi"
    COMPETITIONS_URL = "https://reppi.fi/events"
    
    # Known API endpoints to try
    API_ENDPOINTS = [
        "https://reppi.fi/api/events",
        "https://reppi.fi/api/competitions",
        "https://reppi.fi/api/calendar/events",
        "https://reppi.fi/api/v1/events",
    ]
    
    # Known competitions as fallback (Finnish + International)
    FALLBACK_COMPETITIONS = [
        # Finnish competitions
        {
            "name": "Turku Tuomiopäivä",
            "date_start": "2026-06-11",
            "date_end": "2026-06-13",
            "location": "Turku",
            "country": "Finland",
            "level": "elite",
            "info_url": "https://reppi.fi/events",
            "description": "Suomen suurin crossfit-kisa"
        },
        {
            "name": "Yyteri Sandstorm",
            "date_start": "2026-07-06",
            "date_end": "2026-07-26",
            "location": "Yyteri, Pori",
            "country": "Finland",
            "level": "elite",
            "info_url": "https://reppi.fi/events",
            "description": "Finaalitapahtuma"
        },
        {
            "name": "Unbroken Karsinnat",
            "date_start": "2026-07-06",
            "date_end": "2026-07-26",
            "location": "Online",
            "country": "Finland",
            "level": "hobby",
            "info_url": "https://reppi.fi/events",
            "description": "Unbroken-kisojen karsinnat"
        },
        {
            "name": "Unbroken Finaalit",
            "date_start": "2026-09-25",
            "date_end": "2026-09-27",
            "location": "Vantaa",
            "country": "Finland",
            "level": "elite",
            "info_url": "https://reppi.fi/events",
            "description": "Unbroken-kisojen finaalit"
        },
        {
            "name": "Vaasa Showdown",
            "date_start": None,
            "date_end": None,
            "location": "Vaasa",
            "country": "Finland",
            "level": "hobby",
            "info_url": "https://reppi.fi/events",
            "description": "SM-karsintakisa"
        },
        {
            "name": "Finnish CrossFit Championship",
            "date_start": None,
            "date_end": None,
            "location": "Helsinki",
            "country": "Finland",
            "level": "elite",
            "info_url": "https://reppi.fi/events",
            "description": "Suomen mestaruuskisat"
        },
        # International elite competitions
        {
            "name": "Wodapalooza Miami Beach",
            "date_start": "2026-03-12",
            "date_end": "2026-03-15",
            "location": "Miami Beach, FL",
            "country": "USA",
            "level": "elite",
            "info_url": "https://wodapalooza.com",
            "youtube_url": "https://www.youtube.com/@WodapaloozaFitnessFestival",
            "description": "Miami Beach Fitness Festival - The largest CrossFit competition in the world"
        },
        {
            "name": "Rogue Invitational",
            "date_start": "2026-10-23",
            "date_end": "2026-10-25",
            "location": "Aberdeen, Scotland",
            "country": "UK",
            "level": "elite",
            "info_url": "https://roguefitness.com/invitational",
            "youtube_url": "https://www.youtube.com/@RogueFitness",
            "description": "The Rogue Invitational - World's strongest CrossFit and Strongman competition"
        },
        # World Fitness Project (WFP) 2026
        {
            "name": "WFP Tour Stop 1 - London Pro",
            "date_start": "2026-05-01",
            "date_end": "2026-05-03",
            "location": "Drumsheds, London",
            "country": "UK",
            "level": "elite",
            "info_url": "https://worldfitnessproject.com/tour/tour-stop-1",
            "youtube_url": "https://www.youtube.com/@WorldFitnessProject",
            "description": "World Fitness Tour Stop 1 - Pro Men, Pro Women, Elite Teams"
        },
        {
            "name": "WFP Tour Stop 2 - Grand Park Pro",
            "date_start": "2026-08-28",
            "date_end": "2026-08-30",
            "location": "Grand Park, Westfield, Indiana",
            "country": "USA",
            "level": "elite",
            "info_url": "https://worldfitnessproject.com/tour/tour-overview",
            "youtube_url": "https://www.youtube.com/@WorldFitnessProject",
            "description": "World Fitness Tour Stop 2 - Pro Men, Pro Women, Elite Teams"
        },
        {
            "name": "WFP World Fitness Finals",
            "date_start": "2026-12-17",
            "date_end": "2026-12-20",
            "location": "Bella Center, Copenhagen",
            "country": "Denmark",
            "level": "elite",
            "info_url": "https://www.worldfitnessproject.com/world-fitness-finals",
            "youtube_url": "https://www.youtube.com/@WorldFitnessProject",
            "description": "World Fitness Finals - Season culmination with Pro Finals, Elite Teams, Age Groups"
        },
        # WFP Partner Competitions 2026
        {
            "name": "Athens Throwdown (WFP Partner)",
            "date_start": "2026-04-17",
            "date_end": "2026-04-19",
            "location": "Athens",
            "country": "Greece",
            "level": "elite",
            "info_url": "https://worldfitnessproject.com/tour/tour-overview",
            "description": "WFP Partner Competition - Elite Teams, Masters Individual qualifier"
        },
        {
            "name": "Oslo Throwdown (WFP Partner)",
            "date_start": "2026-10-09",
            "date_end": "2026-10-11",
            "location": "Oslo",
            "country": "Norway",
            "level": "elite",
            "info_url": "https://worldfitnessproject.com/tour/tour-overview",
            "description": "WFP Partner Competition - Elite Teams, Masters Individual qualifier"
        }
    ]
    
    def __init__(self, max_retries: int = 3, retry_delay: float = 2.0):
        """
        Initialize scraper.
        
        Args:
            max_retries: Maximum number of retries for failed requests
            retry_delay: Delay between retries in seconds
        """
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'fi-FI,fi;q=0.9,en-US;q=0.8,en;q=0.7',
        })
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.use_playwright = False
        
        # Try to import playwright
        try:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright
            self.use_playwright = True
            logger.info("Playwright available for JavaScript rendering")
        except ImportError:
            logger.warning("Playwright not available, using requests only")
    
    def fetch_competitions(self) -> List[Competition]:
        """
        Fetch competitions from reppi.fi using multiple strategies.
        
        Returns:
            List of Competition objects
        """
        competitions = []
        
        # Strategy 1: Try API endpoints
        try:
            competitions = self._fetch_from_api()
            if competitions:
                logger.info(f"Found {len(competitions)} competitions from API")
                return competitions
        except Exception as e:
            logger.warning(f"API fetch failed: {e}")
        
        # Strategy 2: Try Playwright if available
        if self.use_playwright:
            try:
                competitions = self._fetch_with_playwright()
                if competitions:
                    logger.info(f"Found {len(competitions)} competitions with Playwright")
                    return competitions
            except Exception as e:
                logger.warning(f"Playwright fetch failed: {e}")
        
        # Strategy 3: Try basic requests scraping
        try:
            competitions = self._fetch_with_requests()
            if competitions:
                logger.info(f"Found {len(competitions)} competitions with requests")
                return competitions
        except Exception as e:
            logger.warning(f"Requests fetch failed: {e}")
        
        # Strategy 4: Fallback to hardcoded competitions
        logger.info("Using fallback competitions")
        return self._get_fallback_competitions()
    
    def _fetch_from_api(self) -> List[Competition]:
        """Try to fetch from API endpoints."""
        for endpoint in self.API_ENDPOINTS:
            try:
                logger.info(f"Trying API endpoint: {endpoint}")
                response = self.session.get(endpoint, timeout=10)
                
                if response.status_code == 200:
                    content_type = response.headers.get('Content-Type', '')
                    
                    if 'application/json' in content_type:
                        data = response.json()
                        competitions = self._parse_api_response(data)
                        if competitions:
                            return competitions
                    elif 'text/html' not in content_type:
                        # Might be JSON without proper content-type
                        try:
                            data = response.json()
                            competitions = self._parse_api_response(data)
                            if competitions:
                                return competitions
                        except json.JSONDecodeError:
                            pass
                            
            except requests.RequestException as e:
                logger.debug(f"API endpoint {endpoint} failed: {e}")
                continue
        
        return []
    
    def _parse_api_response(self, data) -> List[Competition]:
        """Parse API response into Competition objects."""
        competitions = []
        
        # Handle different API response formats
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            # Try common keys
            for key in ['events', 'competitions', 'data', 'items', 'results']:
                if key in data:
                    items = data[key]
                    break
            else:
                items = [data] if data else []
        else:
            return []
        
        for item in items:
            try:
                comp = self._parse_api_item(item)
                if comp:
                    competitions.append(comp)
            except Exception as e:
                logger.debug(f"Failed to parse API item: {e}")
                continue
        
        return competitions
    
    def _parse_api_item(self, item: Dict) -> Optional[Competition]:
        """Parse a single API item into Competition."""
        # Extract name
        name = item.get('name') or item.get('title') or item.get('eventName')
        if not name:
            return None
        
        # Extract dates
        date_start = self._parse_date(item.get('startDate') or item.get('dateStart') or item.get('date'))
        date_end = self._parse_date(item.get('endDate') or item.get('dateEnd'))
        
        # Extract location
        location = item.get('location') or item.get('city') or item.get('venue') or "Suomi"
        
        # Extract URL
        info_url = item.get('url') or item.get('link') or item.get('eventUrl')
        if info_url and not info_url.startswith('http'):
            info_url = self.BASE_URL + info_url
        
        # Classify level
        level = self._classify_level(name + ' ' + str(item.get('description', '')))
        
        return Competition(
            name=name,
            date_start=date_start,
            date_end=date_end,
            location=location,
            country="Finland",
            level=level,
            info_url=info_url,
            description=item.get('description', ''),
            price=item.get('price') or item.get('fee'),
            categories=item.get('categories', []) or item.get('ageGroups', [])
        )
    
    def _fetch_with_playwright(self) -> List[Competition]:
        """Fetch competitions using Playwright with retry logic."""
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Playwright attempt {attempt + 1}/{self.max_retries}")
                
                with self._playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(
                        viewport={'width': 1920, 'height': 1080},
                        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                    )
                    page = context.new_page()
                    
                    # Navigate to page
                    page.goto(self.COMPETITIONS_URL, wait_until='domcontentloaded', timeout=30000)
                    
                    # Wait for Angular to load
                    page.wait_for_timeout(3000)
                    
                    # Try to wait for content
                    try:
                        # Wait for common selectors
                        selectors = [
                            '.event-card',
                            '.event-item',
                            '[class*="event"]',
                            'article',
                            '.competition',
                            '.card'
                        ]
                        
                        for selector in selectors:
                            try:
                                page.wait_for_selector(selector, timeout=5000)
                                logger.info(f"Found content with selector: {selector}")
                                break
                            except PlaywrightTimeout:
                                continue
                    except Exception:
                        pass
                    
                    # Additional wait for dynamic content
                    page.wait_for_timeout(2000)
                    
                    # Get page content
                    html_content = page.content()
                    browser.close()
                    
                    # Parse the content
                    competitions = self._parse_html_content(html_content)
                    if competitions:
                        return competitions
                    
            except Exception as e:
                logger.warning(f"Playwright attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))  # Exponential backoff
                continue
        
        return []
    
    def _fetch_with_requests(self) -> List[Competition]:
        """Fetch competitions using requests."""
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(self.COMPETITIONS_URL, timeout=30)
                response.raise_for_status()
                return self._parse_html_content(response.text)
            except requests.RequestException as e:
                logger.warning(f"Requests attempt {attempt + 1} failed: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                continue
        return []
    
    def _parse_html_content(self, html: str) -> List[Competition]:
        """Parse HTML content for competitions."""
        competitions = []
        soup = BeautifulSoup(html, 'html.parser')
        
        # Try multiple selectors
        selectors = [
            '.event-card',
            '.event-item',
            '.competition-card',
            '.event',
            '[class*="event"]',
            'article',
            '.card',
            '.event-list-item',
            '[data-testid*="event"]'
        ]
        
        events = []
        for selector in selectors:
            events = soup.select(selector)
            if events:
                logger.debug(f"Found {len(events)} elements with selector '{selector}'")
                break
        
        if not events:
            # Fallback: search for any structured content
            events = soup.find_all(['article', 'div', 'section'], 
                class_=re.compile(r'event|competition|kisa|kilpailu', re.I))
        
        for event in events:
            try:
                comp = self._parse_event_element(event)
                if comp:
                    competitions.append(comp)
            except Exception as e:
                logger.debug(f"Failed to parse event element: {e}")
                continue
        
        return competitions
    
    def _parse_event_element(self, event) -> Optional[Competition]:
        """Parse a single event element from HTML."""
        # Extract name
        name_elem = (event.find(['h2', 'h3', 'h4']) or 
                    event.find(class_=re.compile(r'title|name|nimi', re.I)) or
                    event.find('a'))
        name = name_elem.get_text(strip=True) if name_elem else None
        
        if not name:
            return None
        
        # Look for date
        date_elem = (event.find(class_=re.compile(r'date|time|aika|päivä', re.I)) or
                    event.find('time'))
        date_str = date_elem.get_text(strip=True) if date_elem else None
        
        if not date_str:
            text = event.get_text()
            date_match = re.search(r'\d{1,2}\.\s*[a-zäöå]+\s*\d{4}', text, re.I)
            if date_match:
                date_str = date_match.group(0)
        
        date_start, date_end = self._extract_date_range(date_str) if date_str else (None, None)
        
        # Location
        location_elem = (event.find(class_=re.compile(r'location|place|paikka|sijainti', re.I)) or
                        event.find(class_=re.compile(r'city|kaupunki', re.I)))
        location = location_elem.get_text(strip=True) if location_elem else "Suomi"
        
        # Links
        link_elem = event.find('a', href=True)
        info_url = None
        if link_elem:
            href = link_elem['href']
            if href.startswith('http'):
                info_url = href
            elif href.startswith('/'):
                info_url = self.BASE_URL + href
            else:
                info_url = self.BASE_URL + '/' + href
        
        # Classify level
        text_for_classification = (name + ' ' + event.get_text()).lower()
        level = self._classify_level(text_for_classification)
        
        # Description
        desc_elem = event.find(class_=re.compile(r'description|desc|kuvaus|info', re.I))
        description = desc_elem.get_text(strip=True) if desc_elem else ""
        if not description:
            description = f"Finnish CrossFit competition. Source: reppi.fi"
        
        return Competition(
            name=name,
            date_start=date_start,
            date_end=date_end,
            location=location,
            country="Finland",
            level=level,
            info_url=info_url,
            description=description
        )
    
    def _get_fallback_competitions(self) -> List[Competition]:
        """Return hardcoded fallback competitions."""
        competitions = []
        
        for data in self.FALLBACK_COMPETITIONS:
            try:
                date_start = None
                if data.get("date_start"):
                    date_start = datetime.strptime(data["date_start"], "%Y-%m-%d")
                
                date_end = None
                if data.get("date_end"):
                    date_end = datetime.strptime(data["date_end"], "%Y-%m-%d")
                
                comp = Competition(
                    name=data["name"],
                    date_start=date_start,
                    date_end=date_end,
                    location=data["location"],
                    country=data["country"],
                    level=CompetitionLevel(data["level"]),
                    info_url=data.get("info_url"),
                    description=data.get("description", "")
                )
                competitions.append(comp)
            except Exception as e:
                logger.warning(f"Failed to create fallback competition {data.get('name')}: {e}")
        
        return competitions
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse various date formats."""
        if not date_str:
            return None
        
        date_str = str(date_str).strip()
        
        # Try ISO format
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except ValueError:
            pass
        
        # Try common formats
        formats = [
            '%Y-%m-%d',
            '%d.%m.%Y',
            '%d.%m.%y',
            '%d/%m/%Y',
            '%Y/%m/%d',
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        # Try Finnish date format
        return self._parse_finnish_date(date_str)
    
    def _parse_finnish_date(self, date_str: str) -> Optional[datetime]:
        """Parse Finnish date format to datetime."""
        if not date_str:
            return None
        
        date_str = date_str.strip().lower()
        
        months = {
            'tammikuu': 1, 'tammi': 1, 'tammikuuta': 1,
            'helmikuu': 2, 'helmi': 2, 'helmikuuta': 2,
            'maaliskuu': 3, 'maalis': 3, 'maaliskuuta': 3,
            'huhtikuu': 4, 'huhti': 4, 'huhtikuuta': 4,
            'toukokuu': 5, 'touko': 5, 'toukokuuta': 5,
            'kesäkuu': 6, 'kesä': 6, 'kesäkuuta': 6,
            'heinäkuu': 7, 'heinä': 7, 'heinäkuuta': 7,
            'elokuu': 8, 'elo': 8, 'elokuuta': 8,
            'syyskuu': 9, 'syys': 9, 'syyskuuta': 9,
            'lokakuu': 10, 'loka': 10, 'lokakuuta': 10,
            'marraskuu': 11, 'marras': 11, 'marraskuuta': 11,
            'joulukuu': 12, 'joulu': 12, 'joulukuuta': 12
        }
        
        # Pattern: "5. kesäkuuta 2026" or "5.6.2026"
        patterns = [
            r'(\d{1,2})\.?\s*([a-zäöå]+)\s+(\d{4})',
            r'(\d{1,2})\.(\d{1,2})\.(\d{4})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, date_str)
            if match:
                try:
                    day = int(match.group(1))
                    month_str = match.group(2)
                    year = int(match.group(3))
                    
                    if month_str.isdigit():
                        month = int(month_str)
                    else:
                        month = months.get(month_str)
                    
                    if month:
                        return datetime(year, month, day)
                except (ValueError, IndexError):
                    continue
        
        return None
    
    def _extract_date_range(self, date_str: str) -> Tuple[Optional[datetime], Optional[datetime]]:
        """Extract start and end dates from Finnish date range string."""
        if not date_str:
            return None, None
        
        date_str = date_str.strip().lower()
        
        # Pattern: "5.–7. kesäkuuta 2026" or "5.-7.6.2026"
        range_pattern = r'(\d{1,2})\.?\s*[–-]\s*(\d{1,2})\.?\s*([a-zäöå]+)?\.?\s*(\d{4})'
        match = re.search(range_pattern, date_str)
        
        if match:
            try:
                start_day = int(match.group(1))
                end_day = int(match.group(2))
                month_str = match.group(3) if match.group(3) else None
                year = int(match.group(4))
                
                months = {
                    'tammikuu': 1, 'tammi': 1, 'helmikuu': 2, 'helmi': 2,
                    'maaliskuu': 3, 'maalis': 3, 'huhtikuu': 4, 'huhti': 4,
                    'toukokuu': 5, 'touko': 5, 'kesäkuu': 6, 'kesä': 6,
                    'heinäkuu': 7, 'heinä': 7, 'elokuu': 8, 'elo': 8,
                    'syyskuu': 9, 'syys': 9, 'lokakuu': 10, 'loka': 10,
                    'marraskuu': 11, 'marras': 11, 'joulukuu': 12, 'joulu': 12
                }
                
                month = months.get(month_str, datetime.now().month) if month_str else datetime.now().month
                
                start_date = datetime(year, month, start_day)
                end_date = datetime(year, month, end_day)
                return start_date, end_date
            except (ValueError, IndexError):
                pass
        
        # Single date
        single_date = self._parse_finnish_date(date_str)
        return single_date, None
    
    def _classify_level(self, text: str) -> CompetitionLevel:
        """Classify competition as hobby or elite based on text."""
        text_lower = text.lower()
        
        elite_keywords = [
            'elite', 'pro', 'games', 'sm-', 'sm ', 'mestaruus', 
            'championship', 'finaali', 'final', 'quarterfinal', 
            'semifinal', 'unbroken', 'sandstorm', 'tuomiopäivä', 'showdown'
        ]
        
        amateur_keywords = [
            'kuntosarja', 'harraste', 'hupisarja', 'beginner',
            'avoin', 'scramble', 'throwdown', 'hobby'
        ]
        
        if any(kw in text_lower for kw in elite_keywords):
            return CompetitionLevel.ELITE
        elif any(kw in text_lower for kw in amateur_keywords):
            return CompetitionLevel.HOBBY
        else:
            return CompetitionLevel.UNKNOWN
    
    def fetch_competition_details(self, competition_url: str) -> Dict:
        """
        Fetch detailed information about a specific competition.
        
        Args:
            competition_url: URL of the competition page
            
        Returns:
            Dictionary with detailed information
        """
        details = {
            'url': competition_url,
            'description': '',
            'registration_end': None,
            'price': None,
            'youtube_link': None,
            'categories': [],
            'venue': None
        }
        
        try:
            response = self.session.get(competition_url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract description
            desc_elem = soup.find('div', class_=re.compile(r'description|info|kuvaus', re.I))
            if desc_elem:
                details['description'] = desc_elem.get_text(strip=True)
            
            # Look for YouTube links
            youtube_links = soup.find_all('a', href=re.compile(r'youtube\.com|youtu\.be', re.I))
            if youtube_links:
                details['youtube_link'] = youtube_links[0]['href']
            
            # Look for price
            price_text = soup.find(text=re.compile(r'\d+\s*€'))
            if price_text:
                details['price'] = price_text.strip()
            
            # Look for registration end date
            reg_end = soup.find(text=re.compile(r'ilmoittautuminen päättyy|registration ends', re.I))
            if reg_end:
                date_match = re.search(r'\d{1,2}\.\s*\d{1,2}\.\s*\d{4}', reg_end)
                if date_match:
                    details['registration_end'] = date_match.group(0)
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch competition details: {e}")
        
        return details


def main():
    """Test the scraper."""
    scraper = ReppiScraper()
    competitions = scraper.fetch_competitions()
    
    print(f"\nFound {len(competitions)} competitions:\n")
    for comp in competitions:
        print(f"  📅 {comp.name}")
        print(f"     Level: {comp.level.value}")
        print(f"     Date: {comp.date_start.strftime('%d.%m.%Y') if comp.date_start else 'TBA'}")
        print(f"     Location: {comp.location}")
        if comp.info_url:
            print(f"     URL: {comp.info_url}")
        print()


if __name__ == '__main__':
    main()

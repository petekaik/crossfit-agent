"""
CrossFit & Functional Fitness Competition Scrapers

Active scrapers (2026-05-01):
  1. CrossFitGamesScraper    – Official CrossFit season (Games + 16 Semifinal events)
  2. WFPCompetitionScraper   – World Fitness Project Tour Stops + Finals + Partners
  3. HYROXScraper            – HYROX Nordic/European events
  4. ReppiScraper            – Finnish competitions (reppi.fi fallback)
  5. EliteEventScraper       – Independent elite events (Rogue, Wodapalooza, CRASH, iF3, etc.)

Source verification:
  - CrossFit Games: games.crossfit.com/article/2026-crossfit-semifinals-dates-and-details (2025-10-29)
  - WFP: worldfitnessproject.com/tour/tour-overview
  - HYROX: hyrox.com/event/hyrox-helsinki/
  - Calendar: thebarbellspin.com/competition/2026-crossfit-calendar...
"""

import json
import re
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Data Models
# ──────────────────────────────────────────────

class CompetitionLevel(Enum):
    HOBBY = "hobby"
    ELITE = "elite"

class EventType(Enum):
    """What kind of event this is."""
    CROSSFIT_GAMES = "crossfit_games"
    CROSSFIT_SEMIFINAL = "crossfit_semifinal"
    WFP_TOUR = "wfp_tour"
    WFP_PARTNER = "wfp_partner"
    HYROX = "hyrox"
    INDEPENDENT_ELITE = "independent_elite"
    FINNISH = "finnish"

@dataclass
class Competition:
    name: str
    date_start: Optional[datetime]
    date_end: Optional[datetime]
    location: str
    country: str
    level: CompetitionLevel
    event_type: EventType = EventType.INDEPENDENT_ELITE
    youtube_url: Optional[str] = None
    ticket_url: Optional[str] = None
    info_url: Optional[str] = None
    description: str = ""
    is_all_day: bool = False           # True = season period, all-day calendar event
    video_feeds: List[Dict[str, str]] = field(default_factory=list)  # e.g. [{"label": "Morning", "url": "..."}]


# ──────────────────────────────────────────────
# Helper: parse dates from YYYY-MM-DD strings
# ──────────────────────────────────────────────

def _d(date_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO date string. Returns None if missing."""
    if not date_str:
        return None
    return datetime.strptime(date_str, "%Y-%m-%d")

def _c(name, start, end, location, country, level, event_type=EventType.INDEPENDENT_ELITE,
       youtube=None, ticket=None, info=None, description="", is_all_day=False, video_feeds=None):
    """Factory for Competition with optional end date."""
    return Competition(
        name=name,
        date_start=_d(start),
        date_end=_d(end) or (_d(start) if start and not end else None),
        location=location,
        country=country,
        level=level,
        event_type=event_type,
        youtube_url=youtube,
        ticket_url=ticket,
        info_url=info,
        description=description,
        is_all_day=is_all_day,
        video_feeds=video_feeds or [],
    )


# ──────────────────────────────────────────────
# 1. CrossFit Games Scraper
# ──────────────────────────────────────────────

class CrossFitGamesScraper:
    """Official CrossFit Games season events.

    Source: games.crossfit.com/article/2026-crossfit-semifinals-dates-and-details
    """

    CF_YOUTUBE = "https://www.youtube.com/@CrossFitGamesTV"
    BASE_URL = "https://games.crossfit.com"

    # 2026 individual in-person semifinals + online events
    # EET times from games.crossfit.com/semifinals/schedule
    SEMIFINALS_2026 = [
        # (name, start, end, location, country, info_url, ticket_url, youtube, description)
        ("Mayhem Classic",             "2026-04-17", "2026-04-19", "Cookeville, TN",           "USA",
         "https://mayhemclassic.com",
         "https://www.tickettailor.com/events/crossfitmayhem/2069760",
         "https://www.youtube.com/@CFProjectMayhem/streams",
         "CrossFit Semifinal — 3M/3W Games spots\nAikataulu (EET): 10:00–18:00"),
        ("Legends Championship",       "2026-04-24", "2026-04-26", "Del Mar, CA",              "USA",
         "https://legendscomp.com/legends-del-mar/",
         "https://competitioncorner.net/events/20036/merchandise?ticketsOnly=true",
         "https://www.floelite.com/signup?redirect=%2Flive%2F248339",
         "CrossFit Semifinal — Ind 2M/2W + Masters\nAikataulu (EET): 12:00–20:00"),
        ("Copa Sur",                   "2026-05-01", "2026-05-03", "São José, SC",             "Brazil",
         "https://cfcopasur.com/", None, None,
         "CrossFit Semifinal — Ind 2M/2W + 1 Team\nAikataulu (EET): 08:00–16:00"),
        ("Far East Throwdown",         "2026-04-30", "2026-05-03", "Busan",                    "South Korea",
         "https://www.fareastthrowdown.com/", None, None,
         "CrossFit Semifinal — Ind 1M/1W + 1 Team\nAikataulu (EET): 20:00–04:00 (alkaa 30.4.)"),
        ("Magic City Games",           "2026-05-01", "2026-05-03", "Birmingham, AL",           "USA",
         "https://magiccity.games/", None, None,
         "CrossFit Semifinal — Masters only\nAikataulu (EET): 10:00–18:00"),
        ("Age-Group Online Semifinal", "2026-05-07", "2026-05-11", "Virtual",                   "Worldwide",
         None, None, None,
         "CrossFit Semifinal — Masters + Teenagers (online)\nAikataulu (EET): 15:00–15:00"),
        ("French Throwdown",           "2026-05-15", "2026-05-17", "Paris",                    "France",
         "https://www.frenchthrowdown.com/", None,
         "https://www.youtube.com/@FrenchThrowdown",
         "CrossFit Semifinal — Ind 3M/3W + 3 Teams + Masters\nAikataulu (EET): 03:00–13:00"),
        ("Torian Pro",                 "2026-05-21", "2026-05-24", "Brisbane, QLD",            "Australia",
         "https://www.torianpro.com/", None,
         "https://www.youtube.com/c/TYR",
         "CrossFit Semifinal — Ind 3M/3W + 3 Teams + Masters\nAikataulu (EET): 19:00–03:00 (alkaa 21.5.)"),
        ("Rebel Renegade Games",       "2026-05-21", "2026-05-24", "Johannesburg",             "South Africa",
         "https://rebelrenegadegames.com/", None,
         "https://www.youtube.com/@rebelrenegadegames/streams",
         "CrossFit Semifinal — Ind 1M/1W + 1 Team\nAikataulu (EET): 03:00–11:00"),
        ("Syndicate Crown",            "2026-05-29", "2026-05-31", "Knoxville, TN",            "USA",
         "https://www.syndicatecrown.com/", None,
         "https://www.youtube.com/@thebarbellspin",
         "CrossFit Semifinal — Ind 3M/3W + 3 Teams\nAikataulu (EET): 09:00–17:00"),
        ("MAD Fitness Festival",       "2026-05-29", "2026-05-31", "Ciudad Real",              "Spain",
         "https://madfitnessfestival.com/en/home/", None, None,
         "CrossFit Semifinal — Ind 3M/3W + 1 Team\nAikataulu (EET): 03:00–11:00"),
        ("Northern California Classic", "2026-05-29", "2026-05-31", "Sacramento, CA",           "USA",
         "https://thenorcalclassic.com/", None, None,
         "CrossFit Semifinal — Ind 2M/2W\nAikataulu (EET): 12:00–20:00"),
        ("Team Online Semifinals",     "2026-06-04", "2026-06-08", "Virtual",                   "Worldwide",
         None, None, None,
         "CrossFit Semifinal — 7 Teams (online)\nAikataulu (EET): 15:00–15:00"),
        ("Individual Online Semifinals", "2026-06-11", "2026-06-15", "Virtual",                 "Worldwide",
         None, None, None,
         "CrossFit Semifinal — Ind 7M/7W (online)\nAikataulu (EET): 15:00–15:00"),
        ("LatAM Masters",              "2026-06-12", "2026-06-14", "Colombia",                 "Colombia",
         "https://www.latammasters.com/", None,
         "https://www.youtube.com/@LatamMasters/streams",
         "CrossFit Semifinal — Masters only\nAikataulu (EET): 10:00–18:00"),
    ]

    def fetch_season(self) -> List[Competition]:
        comps = []

        # CrossFit Games 2026 (Individual, Teenage, Adaptive)
        comps.append(_c(
            "CrossFit Games 2026", "2026-07-24", "2026-07-26",
            "SAP Center, San Jose, CA", "USA", CompetitionLevel.ELITE,
            EventType.CROSSFIT_GAMES,
            youtube=self.CF_YOUTUBE,
            info=f"{self.BASE_URL}/season/2026",
            description="The ultimate test of fitness — 20th anniversary Games",
        ))

        # Masters Games
        comps.append(_c(
            "Masters CrossFit Games 2026", "2026-07-21", "2026-07-23",
            "San Jose, CA", "USA", CompetitionLevel.ELITE,
            EventType.CROSSFIT_GAMES,
            youtube=self.CF_YOUTUBE,
            description="Masters CrossFit Games",
        ))

        # All semifinal events — online events are season periods (all-day)
        ONLINE_SEMIS = {"Age-Group Online Semifinal", "Team Online Semifinals",
                        "Individual Online Semifinals"}
        for name, start, end, loc, country, info, ticket, yt, desc in self.SEMIFINALS_2026:
            is_ad = name in ONLINE_SEMIS
            comps.append(_c(
                name, start, end, loc, country, CompetitionLevel.ELITE,
                EventType.CROSSFIT_SEMIFINAL,
                youtube=yt, ticket=ticket, info=info, description=desc,
                is_all_day=is_ad,
            ))

        # CrossFit Open + Quarterfinals (season periods — all-day)
        comps.append(_c(
            "CrossFit Open 2026", "2026-02-26", "2026-03-16",
            "Worldwide", "Various", CompetitionLevel.ELITE,
            EventType.CROSSFIT_GAMES,
            info=f"{self.BASE_URL}/open",
            description="CrossFit Open — worldwide online qualifier",
            is_all_day=True,
        ))
        comps.append(_c(
            "CrossFit Quarterfinals 2026", "2026-03-26", "2026-03-30",
            "Worldwide", "Various", CompetitionLevel.ELITE,
            EventType.CROSSFIT_GAMES,
            description="CrossFit Quarterfinals — top 25% from Open",
            is_all_day=True,
        ))

        # CrossFit Games 2025 (past, for historical context)
        comps.append(_c(
            "CrossFit Games 2025", "2025-08-01", "2025-08-03",
            "Albany, NY", "USA", CompetitionLevel.ELITE,
            EventType.CROSSFIT_GAMES,
            youtube=self.CF_YOUTUBE,
        ))

        return comps


# ──────────────────────────────────────────────
# 2. World Fitness Project Scraper
# ──────────────────────────────────────────────

class WFPCompetitionScraper:
    """World Fitness Project 2026 season.

    Source: worldfitnessproject.com/tour/tour-overview
    """

    WFP_YOUTUBE = "https://www.youtube.com/@WorldFitnessProject"

    def fetch_competitions(self) -> List[Competition]:
        comps = []

        # Tour Stops
        comps.append(_c(
            "WFP Tour Stop 1 — London Pro", "2026-05-01", "2026-05-03",
            "Drumsheds, London", "UK", CompetitionLevel.ELITE,
            EventType.WFP_TOUR,
            youtube=self.WFP_YOUTUBE,
            info="https://worldfitnessproject.com/tour/tour-stop-1",
            ticket="https://www.worldfitnessproject.com/tour/tickets",
            description="Pro Men/Women (50 athletes) + Elite Teams (20) + Project 1",
        ))
        comps.append(_c(
            "WFP Tour Stop 2 — Grand Park Pro", "2026-08-28", "2026-08-30",
            "Grand Park, Westfield, IN", "USA", CompetitionLevel.ELITE,
            EventType.WFP_TOUR,
            youtube=self.WFP_YOUTUBE,
            info="https://worldfitnessproject.com/tour/tour-overview",
            description="Pro Men/Women (50) + Elite Teams (20) + Project 1",
        ))

        # World Fitness Finals
        comps.append(_c(
            "WFP World Fitness Finals", "2026-12-17", "2026-12-20",
            "Bella Center, Copenhagen", "Denmark", CompetitionLevel.ELITE,
            EventType.WFP_TOUR,
            youtube=self.WFP_YOUTUBE,
            info="https://www.worldfitnessproject.com/world-fitness-finals",
            description="Season finale — Pro, Teams, Age Groups + Project 1",
        ))

        # Partner competitions
        comps.append(_c(
            "Athens Throwdown (WFP Partner)", "2026-04-17", "2026-04-19",
            "Athens", "Greece", CompetitionLevel.ELITE,
            EventType.WFP_PARTNER,
            description="WFP partner — 1st place → Finals invite (past event)",
        ))
        comps.append(_c(
            "Monster Games (WFP Partner)", "2026-07-24", "2026-07-26",
            "Overland Park, KS", "USA", CompetitionLevel.ELITE,
            EventType.WFP_PARTNER,
            description="WFP partner — Masters 35-55+ Finals invite",
        ))
        comps.append(_c(
            "Heart of America (WFP Partner)", "2026-10-09", "2026-10-11",
            "Springfield, MO", "USA", CompetitionLevel.ELITE,
            EventType.WFP_PARTNER,
            description="WFP partner — Elite Teams Finals invite",
        ))
        comps.append(_c(
            "Oslo Throwdown (WFP Partner)", "2026-10-09", "2026-10-11",
            "Oslo", "Norway", CompetitionLevel.ELITE,
            EventType.WFP_PARTNER,
            description="WFP partner event",
        ))

        # Online qualifiers (season periods — all-day)
        for name, dates, desc in [
            ("WFP Tour Stop 1 Qualifier", ("2026-02-18", "2026-03-04"),
             "Online qualifier for London Pro"),
            ("WFP Tour Stop 2 Qualifier", ("2026-07-01", "2026-07-08"),
             "Online qualifier for Grand Park Pro"),
            ("WFP Finals Qualifier", ("2026-09-23", "2026-09-30"),
             "Online qualifier for World Fitness Finals"),
        ]:
            comps.append(_c(
                name, dates[0], dates[1],
                "Online", "Worldwide", CompetitionLevel.ELITE,
                EventType.WFP_TOUR,
                info="https://worldfitnessproject.com/tour/tour-overview",
                description=desc,
                is_all_day=True,
            ))

        return comps


# ──────────────────────────────────────────────
# 3. HYROX Scraper
# ──────────────────────────────────────────────

class HYROXScraper:
    """HYROX fitness racing events — Nordic + European focus.

    Source: hyrox.com, gowod.app/blog/hyrox-2026-race-calendar
    """

    HYROX_YOUTUBE = "https://www.youtube.com/@HYROX"

    def fetch_competitions(self) -> List[Competition]:
        comps = []

        # Nordic / nearby events most relevant to Finland
        comps.append(_c(
            "HYROX Helsinki", "2026-05-09", "2026-05-10",
            "Messukeskus, Helsinki", "Finland", CompetitionLevel.ELITE,
            EventType.HYROX,
            youtube=self.HYROX_YOUTUBE,
            info="https://hyrox.com/event/hyrox-helsinki/",
            description="HYROX makes its Finland debut — 8km run + 8 functional stations",
        ))
        comps.append(_c(
            "HYROX Stockholm", "2026-04-04", "2026-04-05",
            "Stockholm", "Sweden", CompetitionLevel.ELITE,
            EventType.HYROX,
            youtube=self.HYROX_YOUTUBE,
            description="HYROX Stockholm",
        ))
        comps.append(_c(
            "HYROX Copenhagen", "2026-03-14", "2026-03-15",
            "Copenhagen", "Denmark", CompetitionLevel.ELITE,
            EventType.HYROX,
            youtube=self.HYROX_YOUTUBE,
            description="HYROX Copenhagen",
        ))

        # Major European championships
        comps.append(_c(
            "HYROX European Championships", "2026-05-29", "2026-05-31",
            "Vienna", "Austria", CompetitionLevel.ELITE,
            EventType.HYROX,
            youtube=self.HYROX_YOUTUBE,
            description="HYROX European Championships — elite qualification",
        ))
        comps.append(_c(
            "HYROX World Championships", "2026-06-12", "2026-06-14",
            "Chicago, IL", "USA", CompetitionLevel.ELITE,
            EventType.HYROX,
            youtube=self.HYROX_YOUTUBE,
            description="HYROX World Championships 2026",
        ))

        # Other Nordic/European events
        for name, start, end, loc, country in [
            ("HYROX Oslo",     "2026-11-07", "2026-11-08", "Oslo",      "Norway"),
            ("HYROX Hamburg",  "2026-10-17", "2026-10-18", "Hamburg",   "Germany"),
            ("HYROX Berlin",   "2026-03-21", "2026-03-22", "Berlin",    "Germany"),
            ("HYROX London",   "2026-04-11", "2026-04-12", "London",    "UK"),
        ]:
            comps.append(_c(
                name, start, end, loc, country, CompetitionLevel.ELITE,
                EventType.HYROX,
                youtube=self.HYROX_YOUTUBE,
            ))

        return comps


# ──────────────────────────────────────────────
# 4. Reppi.fi Scraper (Finnish competitions)
# ──────────────────────────────────────────────

class ReppiScraper:
    """Finnish CrossFit competitions from reppi.fi.

    API endpoints tested (all returned empty/error — site uses Angular SPA):
      - /api/events, /api/competitions, /api/calendar/events, /api/v1/events

    Falls back to verified known competitions. Updated periodically.
    """

    BASE_URL = "https://reppi.fi"

    # Verified 2026 Finnish competitions
    FINNISH_EVENTS = [
        {
            "name": "Turku Tuomiopäivä",
            "date_start": "2026-06-11", "date_end": "2026-06-13",
            "location": "Turku", "level": "elite",
            "description": "Suomen suurin crossfit-kisa — elite + hobby divisions",
        },
        {
            "name": "Yyteri Sandstorm",
            "date_start": "2026-07-06", "date_end": "2026-07-26",
            "location": "Yyteri, Pori", "level": "elite",
            "description": "Finaalitapahtuma Yyterissä — elite + hobby",
            "is_all_day": True,
        },
        {
            "name": "Unbroken Karsinnat",
            "date_start": "2026-07-06", "date_end": "2026-07-26",
            "location": "Online", "level": "hobby",
            "description": "Unbroken-kisojen online-karsinnat",
            "is_all_day": True,
        },
        {
            "name": "Unbroken Finaalit",
            "date_start": "2026-09-25", "date_end": "2026-09-27",
            "location": "Vantaa", "level": "elite",
            "description": "Unbroken-kisojen finaalit Vantaalla",
        },
        {
            "name": "Vaasa Showdown",
            "date_start": None, "date_end": None,
            "location": "Vaasa", "level": "hobby",
            "description": "SM-karsintakisa — TBA",
        },
        {
            "name": "Finnish CrossFit Championship",
            "date_start": None, "date_end": None,
            "location": "Helsinki", "level": "elite",
            "description": "Suomen mestaruuskisat — TBA",
        },
    ]

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })

    def fetch_competitions(self) -> List[Competition]:
        """Fetch Finnish competitions. Uses fallback data since reppi.fi APIs are down."""
        comps = []

        for data in self.FINNISH_EVENTS:
            try:
                level = CompetitionLevel.ELITE if data["level"] == "elite" else CompetitionLevel.HOBBY
                comps.append(_c(
                    data["name"], data["date_start"], data["date_end"],
                    data["location"], "Finland", level,
                    EventType.FINNISH,
                    info=f"{self.BASE_URL}/events",
                    description=data.get("description", ""),
                    is_all_day=data.get("is_all_day", False),
                ))
            except Exception as e:
                logger.warning(f"Error creating Finnish event {data['name']}: {e}")

        logger.info(f"ReppiScraper: {len(comps)} Finnish competitions loaded")
        return comps


# ──────────────────────────────────────────────
# 5. Elite Independent Events Scraper
# ──────────────────────────────────────────────

class EliteEventScraper:
    """Independent elite functional fitness events.

    Sources:
      - thebarbellspin.com/competition/2026-crossfit-calendar...
      - boxrox.com/9-top-functional-fitness-events-in-the-usa-in-2026/
      - Event official websites
    """

    def fetch_competitions(self) -> List[Competition]:
        comps = []

        events = [
            # Major independent elite events
            ("Wodapalooza Miami Beach",   "2026-03-12", "2026-03-15",
             "Miami Beach, FL", "USA",
             "https://wodapalooza.com",
             "https://www.youtube.com/@WodapaloozaFitnessFestival",
             "Largest fitness festival — elite + community. Past event."),
            ("Wodapalooza SoCal",        None, None,
             "Southern California", "USA",
             "https://wodapalooza.com",
             None,
             "September 2026 — dates TBA"),
            ("Rogue Invitational",       "2026-10-23", "2026-10-25",
             "Aberdeen, Scotland", "UK",
             "https://roguefitness.com/invitational",
             "https://www.youtube.com/@RogueFitness",
             "World's strongest CrossFit + Strongman invitational"),
            ("TYR Wodapalooza Miami",    "2026-03-12", "2026-03-15",
             "Miami Beach, FL", "USA",
             "https://wodapalooza.com",
             "https://www.youtube.com/@WodapaloozaFitnessFestival",
             "TYR Wodapalooza — elite + community. Past event."),

            # CRASH events (strongman + functional fitness crossover)
            ("CRASH Crescendo",          "2026-04-24", "2026-04-26",
             "TBD", "USA",
             "https://crashcrucible.com", None,
             "CRASH Crescendo — elite functional fitness + strongman"),
            ("CRASH Crucible",           None, None,
             "TBD", "USA",
             "https://crashcrucible.com", None,
             "CRASH Crucible — October 2026, dates TBA"),

            # iF3 (International Functional Fitness Federation)
            ("iF3 Masters World Championships", "2026-10-23", "2026-10-23",
             "TBD", "TBD",
             "https://if3.com", None,
             "iF3 Masters World Championships"),
            ("iF3 World Championships",  None, None,
             "TBD", "TBD",
             "https://if3.com", None,
             "iF3 World Championships — Nov/Dec 2026, TBA"),

            # Other notable elite events
            ("The Fittest Experience (TFX)", "2026-01-30", "2026-02-01",
             "Williamson County, TX", "USA",
             "https://thefittestexperience.com", None,
             "Major early-season elite event. Past event."),
            ("Turf Games",               None, None,
             "London", "UK",
             "https://turfgames.com", None,
             "UK functional fitness — multiple dates TBA"),
            ("ATHX Games",               None, None,
             "UK", "UK",
             "https://athxgames.com", None,
             "UK functional fitness competition — dates TBA"),
        ]

        for name, start, end, loc, country, info, youtube, desc in events:
            comps.append(_c(
                name, start, end, loc, country, CompetitionLevel.ELITE,
                EventType.INDEPENDENT_ELITE,
                info=info, youtube=youtube, description=desc,
            ))

        return comps


# ──────────────────────────────────────────────
# 6. Generic Web Scraper (for dynamic research)
# ──────────────────────────────────────────────

class GenericScraper:
    """Generic web scraper for ad-hoc competition site research."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    def scrape_page(self, url: str) -> Optional[BeautifulSoup]:
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return BeautifulSoup(response.content, "html.parser")
        except Exception as e:
            logger.warning(f"Error fetching {url}: {e}")
            return None

    def extract_dates(self, text: str) -> List[datetime]:
        dates = []
        patterns = [
            r'(\d{1,2})\.(\d{1,2})\.(\d{4})',  # 15.3.2025
            r'(\d{1,2})\.(\d{1,2})',            # 15.3
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                try:
                    if len(match) == 3:
                        day, month, year = map(int, match)
                        dates.append(datetime(year, month, day))
                    elif len(match) == 2:
                        day, month = map(int, match)
                        dates.append(datetime(datetime.now().year, month, day))
                except ValueError:
                    continue
        return dates


# ──────────────────────────────────────────────
# 7. Aggregator — orchestrates all sources
# ──────────────────────────────────────────────

class CompetitionAggregator:
    """Aggregates competitions from all active sources."""

    def __init__(self):
        self.games = CrossFitGamesScraper()
        self.wfp = WFPCompetitionScraper()
        self.hyrox = HYROXScraper()
        self.reppi = ReppiScraper()
        self.elite = EliteEventScraper()
        self.generic = GenericScraper()
        self.competitions: List[Competition] = []

    def fetch_all(self) -> List[Competition]:
        """Fetch from all sources, deduplicate, return sorted list."""
        self.competitions = []

        # Layer 1: CrossFit Games (official season)
        self.competitions.extend(self.games.fetch_season())

        # Layer 2: WFP (World Fitness Project)
        self.competitions.extend(self.wfp.fetch_competitions())

        # Layer 3: HYROX (fitness racing)
        self.competitions.extend(self.hyrox.fetch_competitions())

        # Layer 4: Reppi.fi (Finnish events)
        try:
            self.competitions.extend(self.reppi.fetch_competitions())
        except Exception as e:
            logger.warning(f"ReppiScraper failed: {e}")

        # Layer 5: Independent elite events
        self.competitions.extend(self.elite.fetch_competitions())

        # Deduplicate
        self._deduplicate()

        # Sort by date (future events first, then past, None last)
        def sort_key(c):
            if c.date_start:
                return (0, c.date_start)
            return (1, datetime.max)
        self.competitions.sort(key=sort_key)

        return self.competitions

    def _deduplicate(self):
        """Remove duplicates based on (normalized_name, start_date)."""
        seen = {}
        unique = []

        for comp in self.competitions:
            name_key = comp.name.lower().strip()
            # Normalize: remove "TYR ", "The ", year suffixes, "Miami Beach"→"Miami" for matching
            name_key = re.sub(r'\b(tyr|the)\s+', '', name_key).strip()
            name_key = re.sub(r'\s+\d{4}$', '', name_key).strip()
            name_key = re.sub(r'\bmiami\s*beach\b', 'miami', name_key).strip()
            # Normalize all dash variants (em-dash, en-dash, hyphen) to plain hyphen
            name_key = re.sub(r'[—–-]', '-', name_key).strip()

            if comp.date_start:
                key = f"{name_key}_{comp.date_start.strftime('%Y-%m-%d')}"
            else:
                key = name_key

            if key not in seen:
                seen[key] = comp
                unique.append(comp)
            else:
                existing = seen[key]
                # Keep the one with more data (dates, URLs)
                if comp.date_start and not existing.date_start:
                    unique.remove(existing)
                    seen[key] = comp
                    unique.append(comp)
                elif comp.info_url and not existing.info_url:
                    unique.remove(existing)
                    seen[key] = comp
                    unique.append(comp)
                logger.debug(f"Deduplicated: {comp.name} (matched {existing.name})")

        self.competitions = unique

    def to_json(self) -> str:
        data = []
        for comp in self.competitions:
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
            })
        return json.dumps(data, indent=2, ensure_ascii=False)


# ──────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agg = CompetitionAggregator()
    comps = agg.fetch_all()

    print(f"\n{'='*60}")
    print(f"Total competitions: {len(comps)}")
    print(f"{'='*60}")
    print(agg.to_json())

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
    ATHX = "athx"
    DEKA_FIT = "deka_fit"
    METRIX = "metrix"
    GYM_CLASH = "gym_clash"
    OCR = "ocr"
    OCR_TOUGH_VIKING = "ocr_tough_viking"
    STRONGMAN = "strongman"
    WEIGHTLIFTING = "weightlifting"
    POWERLIFTING = "powerlifting"
    ADVENTURE_RACE = "adventure_race"

# ──────────────────────────────────────────────
# Category → calendar color mapping (Google Calendar colorId)
# ──────────────────────────────────────────────

CATEGORY_COLORS = {
    "crossfit":   "11",  # Bold Red
    "wfp":        "4",   # Flamingo (pink)
    "hyrox":      "5",   # Tangerine (yellow/orange)
    "athx":       "6",   # Tangerine (orange)
    "deka":       "2",   # Sage (green)
    "metrix":     "3",   # Grape (purple)
    "gym_clash":  "4",   # Flamingo
    "ocr":        "10",  # Basil (dark green)
    "strongman":  "11",  # Bold Red
    "weightlifting": "9", # Blueberry (dark blue)
    "powerlifting": "1",  # Lavender
    "adventure":  "7",   # Peacock (teal)
    "finnish":    "3",   # Grape
    "other":      "8",   # Graphite (gray)
}

# Category → short label for event title prefix
CATEGORY_LABELS = {
    "crossfit":   "CrossFit",
    "wfp":        "WFP",
    "hyrox":      "HYROX",
    "athx":       "ATHX",
    "deka":       "DEKA",
    "metrix":     "METRIX",
    "gym_clash":  "Gym Clash",
    "ocr":        "OCR",
    "strongman":  "Strongman",
    "weightlifting": "Painonnosto",
    "powerlifting": "Voimanosto",
    "adventure":  "Seikkailu",
    "finnish":    "Suomi",
    "other":      "",
}

def _category_for_event_type(event_type: EventType) -> str:
    """Map EventType to category key."""
    mapping = {
        EventType.CROSSFIT_GAMES: "crossfit",
        EventType.CROSSFIT_SEMIFINAL: "crossfit",
        EventType.WFP_TOUR: "wfp",
        EventType.WFP_PARTNER: "wfp",
        EventType.HYROX: "hyrox",
        EventType.ATHX: "athx",
        EventType.DEKA_FIT: "deka",
        EventType.METRIX: "metrix",
        EventType.GYM_CLASH: "gym_clash",
        EventType.OCR: "ocr",
        EventType.OCR_TOUGH_VIKING: "ocr",
        EventType.STRONGMAN: "strongman",
        EventType.WEIGHTLIFTING: "weightlifting",
        EventType.POWERLIFTING: "powerlifting",
        EventType.ADVENTURE_RACE: "adventure",
        EventType.FINNISH: "finnish",
        EventType.INDEPENDENT_ELITE: "other",
    }
    return mapping.get(event_type, "other")


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
    category: str = ""                 # Category key for color/title prefix
    color_id: str = ""                 # Google Calendar colorId

    def __post_init__(self):
        if not self.category:
            self.category = _category_for_event_type(self.event_type)
        if not self.color_id:
            self.color_id = CATEGORY_COLORS.get(self.category, "8")


# ──────────────────────────────────────────────
# Helper: parse dates from YYYY-MM-DD strings
# ──────────────────────────────────────────────

def _d(date_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO date string. Returns None if missing."""
    if not date_str:
        return None
    return datetime.strptime(date_str, "%Y-%m-%d")

def _c(name, start, end, location, country, level, event_type=EventType.INDEPENDENT_ELITE,
       youtube=None, ticket=None, info=None, description="", is_all_day=False, video_feeds=None,
       category=None, color_id=None):
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
        category=category or "",
        color_id=color_id or "",
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
# 6. ATHX Games Scraper
# ──────────────────────────────────────────────

class ATHXScraper:
    """ATHX Games 2026 — 11-event functional fitness tour across Europe.

    Source: athxgames.com/events
    """

    ATHX_YOUTUBE = "https://www.youtube.com/@ATHXGames"

    ATHX_EVENTS = [
        ("ATHX Berlin 2026",       "2026-05-16", "2026-05-16", "Arena Halle Berlin",       "Germany",
         "https://athxgames.com/events/01k8b743fr5gaejbckwabswn8d"),
        ("ATHX Dublin 2026",       "2026-05-30", "2026-05-30", "RDS Dublin",               "Ireland",
         "https://athxgames.com/events/01k8b7jd8b2etcvybdqprk9jw1"),
        ("ATHX Glasgow 2026",      "2026-06-20", "2026-06-21", "SEC",                      "UK",
         "https://athxgames.com/events/01k8b7k56e7bca5p1ybdfhgat9"),
        ("ATHX Copenhagen 2026",   "2026-08-15", "2026-08-15", "Bella Centre",             "Denmark",
         "https://athxgames.com/events/01k8b7kghhb3nk1h7gvshdxsjw"),
        ("ATHX Birmingham 2026",   "2026-08-22", "2026-08-23", "NEC Birmingham",           "UK",
         "https://athxgames.com/events/01k8b7ktbk6j2am0j31tdf0v72"),
        ("ATHX Barcelona 2026",    "2026-09-05", "2026-09-05", "Fira Barcelona",           "Spain",
         "https://athxgames.com/events/01k8b7mbq0ck7hj91405k8k4nf"),
        ("ATHX Marseille 2026",    "2026-09-19", "2026-09-19", "Marseille Chanot",         "France",
         "https://athxgames.com/events/01k8b7mm46ynsfm2ygsjvr0wz4"),
        ("ATHX Liverpool 2026",    "2026-10-03", "2026-10-04", "Exhibition Centre L'pool", "UK",
         "https://athxgames.com/events/01k8b7nfsdk5cbdrxf2h0hgy9v"),
        ("ATHX Amsterdam 2026",    "2026-11-07", "2026-11-07", "RAI Amsterdam",            "Netherlands",
         "https://athxgames.com/events/01k8b7nxgwcr70a86vqf2y6ck4"),
        ("ATHX Finals Lisbon 2026","2026-11-27", "2026-11-29", "Lisbon Congress Centre",   "Portugal",
         "https://athxgames.com/events/01kk1b7p4a1pzebw5dd7q2z7wn"),
    ]

    def fetch_competitions(self) -> List[Competition]:
        comps = []
        for name, start, end, loc, country, info in self.ATHX_EVENTS:
            comps.append(_c(
                name, start, end, loc, country, CompetitionLevel.ELITE,
                EventType.ATHX,
                youtube=self.ATHX_YOUTUBE, info=info,
                description="ATHX: 2.5h continuous fitness competition — 6 zones",
            ))
        return comps


# ──────────────────────────────────────────────
# 7. Adventure Race / ARWS Scraper
# ──────────────────────────────────────────────

class AdventureRaceScraper:
    """Adventure Racing World Series + Arctic extreme events.

    Sources: arworldseries.com, adventurerace.fi, arcticescapades.com
    """

    def fetch_competitions(self) -> List[Competition]:
        comps = []

        # ARWS European Series — Endurance Quest Lohja 26.-28.6.2026
        comps.append(_c(
            "Endurance Quest Lohja (ARWS)", "2026-06-26", "2026-06-28",
            "Lohja", "Finland", CompetitionLevel.ELITE,
            EventType.ADVENTURE_RACE,
            info="https://www.arworldseries.com/",
            description="Adventure Racing World Series — European Series. Huipputason seikkailu-urheilu Suomessa! Suunnistus, pyöräily, melonta, köysilajit.",
        ))

        # Adventure Race Rovaniemi
        comps.append(_c(
            "Adventure Race Rovaniemi", "2026-05-23", "2026-05-23",
            "Rovaniemi", "Finland", CompetitionLevel.HOBBY,
            EventType.ADVENTURE_RACE,
            info="https://adventurerace.fi/",
            description="Ounasvaaran maastossa — työyhteisöjen seikkailukisa.",
        ))

        # Arctic Circle Race (past)
        comps.append(_c(
            "Arctic Circle Race", "2026-03-27", "2026-03-29",
            "Sisimiut", "Greenland", CompetitionLevel.ELITE,
            EventType.ADVENTURE_RACE,
            info="https://visitgreenland.com/events/arctic-circle-race/",
            description="160 km seikkailujuoksu arktisissa olosuhteissa. Past event.",
        ))

        return comps


# ──────────────────────────────────────────────
# 8. OCR Scrapers (Tough Viking, Strong Viking, Tough Mudder, Spartan, Red Bull 400)
# ──────────────────────────────────────────────

class OCRScraper:
    """Obstacle Course Racing — multiple major series.

    Sources: toughviking.se, strongviking.com, toughmudder.com, spartan.com, redbull.com
    """

    def fetch_competitions(self) -> List[Competition]:
        comps = []

        # Tough Viking — Nordic OCR, Helsinki-tapahtuma
        comps.append(_c(
            "Tough Viking Helsinki", "2026-08-22", "2026-08-22",
            "Helsinki", "Finland", CompetitionLevel.ELITE,
            EventType.OCR_TOUGH_VIKING,
            info="https://toughviking.se/tough-viking-helsinki/",
            description="Pohjoismaiden suurin OCR. Suomen ainoa Tough Viking -tapahtuma. 8-15 km, estettä.",
        ))

        comps.append(_c(
            "Tough Viking Slottsskogen", "2026-04-25", "2026-04-25",
            "Göteborg", "Sweden", CompetitionLevel.ELITE,
            EventType.OCR,
            info="https://toughviking.se/",
            description="Tough Viking Göteborg — Slottsskogen.",
        ))

        comps.append(_c(
            "Tough Viking Djurgården 5K", "2026-08-22", "2026-08-22",
            "Tukholma", "Sweden", CompetitionLevel.ELITE,
            EventType.OCR,
            info="https://toughviking.se/kungliga-djurgarden-22-augusti/",
            description="Tough Viking Kungl. Djurgården 5K.",
        ))

        # Strong Viking — Benelux + Germany
        comps.append(_c(
            "Strong Viking Hofstade", "2026-05-30", "2026-05-30",
            "Hofstade", "Belgium", CompetitionLevel.ELITE,
            EventType.OCR,
            info="https://strongviking.com/en/events/",
            description="Strong Viking — 4-42 km obstaclerun Belgiassa.",
        ))

        comps.append(_c(
            "Strong Viking Wijchen", "2026-06-12", "2026-06-14",
            "Wijchen", "Netherlands", CompetitionLevel.ELITE,
            EventType.OCR,
            info="https://strongviking.com/en/events/",
            description="Strong Viking Wijchen — 3 päivän OCR-festivaali.",
        ))

        comps.append(_c(
            "Strong Viking Ultra Frankfurt", "2026-07-04", "2026-07-05",
            "Frankfurt", "Germany", CompetitionLevel.ELITE,
            EventType.OCR,
            info="https://strongviking.com/en/events/",
            description="Strong Viking Frankfurt + Ultra Viking (60 km, 135+ estettä).",
        ))

        # Tough Mudder Europe
        comps.append(_c(
            "Tough Mudder Berlin-Brandenburg", "2026-06-13", "2026-06-14",
            "Spargelhof Klaistow", "Germany", CompetitionLevel.ELITE,
            EventType.OCR,
            info="https://toughmudder.de/en/events/berlin-brandenburg-en/",
            description="Tough Mudder Berlin — klassikko-OCR Saksassa.",
        ))

        comps.append(_c(
            "World's Toughest Mudder 2026", None, None,
            "TBD", "USA", CompetitionLevel.ELITE,
            EventType.OCR,
            info="https://toughmudder.com/tough-mudder-endurance-series/",
            description="24h endurance OCR — dates TBA.",
        ))

        # Spartan Race
        comps.append(_c(
            "Spartan World Championship 2026", "2026-10-30", "2026-11-01",
            "Abu Dhabi", "UAE", CompetitionLevel.ELITE,
            EventType.OCR,
            info="https://www.spartan.com/",
            description="Spartan World Championship — Sprint, Super, Beast.",
        ))

        # Red Bull 400
        comps.append(_c(
            "Red Bull 400 Courchevel", "2026-07-10", "2026-07-10",
            "Courchevel", "France", CompetitionLevel.ELITE,
            EventType.OCR,
            info="https://www.redbull.com/us-en/events",
            description="Maailman jyrkin 400m porrasjuoksu hyppyrimäessä.",
        ))

        comps.append(_c(
            "Red Bull 400 Ironwood", "2026-05-09", "2026-05-09",
            "Ironwood, MI", "USA", CompetitionLevel.ELITE,
            EventType.OCR,
            info="https://www.redbull.com/us-en/event-series/rb-400-usa",
            description="Red Bull 400 Copper Peak.",
        ))

        return comps


# ──────────────────────────────────────────────
# 9. DEKA FIT Scraper (Spartan functional fitness)
# ──────────────────────────────────────────────

class DEKAScraper:
    """DEKA FIT 2026 — Spartan's functional fitness event series.

    Source: spartan.com, obstacleracingmedia.com
    """

    DEKA_EVENTS = [
        ("DEKA FIT SoCal (Anaheim)",    "2026-03-21", "2026-03-22", "Anaheim, CA",             "USA"),
        ("DEKA FIT NorCal (Sacramento)","2026-04-25", "2026-04-26", "Sacramento, CA",          "USA"),
        ("DEKA FIT Austin",            "2026-05-09", "2026-05-10", "Austin, TX",               "USA"),
        ("DEKA FIT Denver",            "2026-05-30", "2026-05-30", "Aurora, CO",               "USA"),
        ("DEKA FIT Boston",            "2026-06-26", "2026-06-28", "Boston, MA",               "USA"),
        ("DEKA FIT Chicago",           "2026-07-10", "2026-07-12", "Chicago, IL",              "USA"),
        ("DEKA FIT Philadelphia",      "2026-08-07", "2026-08-09", "Philadelphia, PA",         "USA"),
        ("DEKA FIT Raleigh",           "2026-08-22", "2026-08-23", "Raleigh, NC",              "USA"),
        ("DEKA FIT Ft. Lauderdale",    "2026-09-11", "2026-09-13", "Ft. Lauderdale, FL",       "USA"),
        ("DEKA FIT New York",          "2026-09-25", "2026-09-27", "New York, NY",             "USA"),
        ("DEKA FIT Washington DC",     "2026-11-20", "2026-11-22", "Washington, DC",           "USA"),
    ]

    def fetch_competitions(self) -> List[Competition]:
        comps = []
        for name, start, end, loc, country in self.DEKA_EVENTS:
            comps.append(_c(
                name, start, end, loc, country, CompetitionLevel.ELITE,
                EventType.DEKA_FIT,
                info="https://www.spartan.com/en/race/find-a-race?race-type=deka",
                description="DEKA FIT: 10 functional training zones × 500m run = 5K total. Spartanin nopeimmin kasvava sarja.",
            ))
        return comps


# ──────────────────────────────────────────────
# 10. Red Bull Gym Clash Scraper
# ──────────────────────────────────────────────

class GymClashScraper:
    """Red Bull Gym Clash — team functional fitness competition.

    Source: redbull.com/event-series/red-bull-gym-clash
    """

    def fetch_competitions(self) -> List[Competition]:
        comps = []

        comps.append(_c(
            "Red Bull Gym Clash World Final 2026", None, None,
            "TBD", "TBD", CompetitionLevel.ELITE,
            EventType.GYM_CLASH,
            info="https://www.redbull.com/us-en/event-series/red-bull-gym-clash",
            description="Red Bull Gym Clash — 4 hengen tiimit (2M+2N), 4 functional fitness -haastetta. Kansalliset finaalit → maailmanfinaali. Dates TBA.",
        ))

        return comps


# ──────────────────────────────────────────────
# 11. METRIX Fitness Racing Scraper
# ──────────────────────────────────────────────

class METRIXScraper:
    """METRIX Fitness Racing — UK-pohjainen sarja.

    Source: metrix.fitness
    """

    def fetch_competitions(self) -> List[Competition]:
        comps = []

        comps.append(_c(
            "METRIX London 2026", "2026-02-20", "2026-02-21",
            "Magazine London", "UK", CompetitionLevel.ELITE,
            EventType.METRIX,
            info="https://metrix.fitness/",
            description="METRIX: all-day fitness racing experience. UK:n nopeimmin kasvava sarja. Past event.",
        ))

        comps.append(_c(
            "METRIX Cambridge SIM", "2026-01-17", "2026-01-17",
            "Cambridge", "UK", CompetitionLevel.ELITE,
            EventType.METRIX,
            info="https://metrix.fitness/",
            description="METRIX SIM — gym-tason tapahtuma. Past event.",
        ))

        return comps


# ──────────────────────────────────────────────
# 12. Strength Sports Scraper (Strongman + Weightlifting + Powerlifting)
# ──────────────────────────────────────────────

class StrengthSportsScraper:
    """Strongman, Olympic Weightlifting, Powerlifting — major 2026 events.

    Sources: theworldsstrongestman.com, arnoldsports.com, giants-live.com,
             ewf.sport, powerlifting.sport
    """

    def fetch_competitions(self) -> List[Competition]:
        comps = []

        # ── Strongman ──
        comps.append(_c(
            "Arnold Strongman Classic 2026", "2026-03-06", "2026-03-07",
            "Columbus, OH", "USA", CompetitionLevel.ELITE,
            EventType.STRONGMAN,
            info="https://www.roguefitness.com/arnold-strongman-classic",
            description="Arnold Sports Festival — Strongman Classic + Strongwoman. Past event.",
        ))

        comps.append(_c(
            "Europe's Strongest Man 2026", "2026-04-11", "2026-04-11",
            "Leeds, First Direct Arena", "UK", CompetitionLevel.ELITE,
            EventType.STRONGMAN,
            info="https://giants-live.com/shows/europes-strongest-man-2026/",
            description="Europe's Strongest Man — Giants Live -kiertue. Past event.",
        ))

        comps.append(_c(
            "World's Strongest Man 2026", "2026-04-23", "2026-04-26",
            "Myrtle Beach, SC", "USA", CompetitionLevel.ELITE,
            EventType.STRONGMAN,
            info="https://www.theworldsstrongestman.com/2026-information/",
            description="SBD World's Strongest Man — 25 urheilijaa. Past event.",
        ))

        comps.append(_c(
            "The Strongman Classic 2026", None, None,
            "Royal Albert Hall, London", "UK", CompetitionLevel.ELITE,
            EventType.STRONGMAN,
            info="https://giants-live.com/",
            description="Giants Live — The Strongman Classic. Dates TBA.",
        ))

        # ── Olympic Weightlifting ──
        comps.append(_c(
            "European Weightlifting Championships 2026", "2026-04-19", "2026-04-26",
            "Batumi", "Georgia", CompetitionLevel.ELITE,
            EventType.WEIGHTLIFTING,
            info="https://ewf.sport/2026/01/14/2026-ewf-european-championships/",
            description="Painonnoston EM — 104. edition. Past event.",
        ))

        # ── Powerlifting ──
        comps.append(_c(
            "IPF World Classic Championships 2026", "2026-06-08", "2026-06-14",
            "Druskininkai", "Lithuania", CompetitionLevel.ELITE,
            EventType.POWERLIFTING,
            info="https://www.powerlifting.sport/",
            description="IPF World Classic Open — siirretty Dubaista Liettuaan.",
        ))

        comps.append(_c(
            "WPO Powerlifting Championship Las Vegas", "2026-11-20", "2026-11-22",
            "Las Vegas, NV", "USA", CompetitionLevel.ELITE,
            EventType.POWERLIFTING,
            info="https://www.powerlifting.sport/",
            description="World Powerlifting Organization — Westgate Resort & Casino.",
        ))

        return comps

# ──────────────────────────────────────────────
# 13. Generic Web Scraper (for dynamic research)
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
        self.athx = ATHXScraper()
        self.adventure = AdventureRaceScraper()
        self.ocr = OCRScraper()
        self.deka = DEKAScraper()
        self.gym_clash = GymClashScraper()
        self.metrix = METRIXScraper()
        self.strength = StrengthSportsScraper()
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

        # Layer 6: ATHX Games (11 events)
        self.competitions.extend(self.athx.fetch_competitions())

        # Layer 7: Adventure Racing (ARWS, AR, Arctic)
        self.competitions.extend(self.adventure.fetch_competitions())

        # Layer 8: OCR (Tough Viking, Strong Viking, Tough Mudder, Spartan, Red Bull 400)
        self.competitions.extend(self.ocr.fetch_competitions())

        # Layer 9: DEKA FIT (Spartan functional fitness)
        self.competitions.extend(self.deka.fetch_competitions())

        # Layer 10: Red Bull Gym Clash
        self.competitions.extend(self.gym_clash.fetch_competitions())

        # Layer 11: METRIX Fitness Racing
        self.competitions.extend(self.metrix.fetch_competitions())

        # Layer 12: Strength Sports (Strongman + Weightlifting + Powerlifting)
        self.competitions.extend(self.strength.fetch_competitions())

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
                "category": comp.category,
                "color_id": comp.color_id,
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

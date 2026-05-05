"""
Tests for ReppiScraper
"""

import unittest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

import sys
sys.path.insert(0, '/Users/petekaik/.openclaw/workspace/projects/crossfit-agent/src')

from reppi_scraper import ReppiScraper, Competition, CompetitionLevel


class TestReppiScraper(unittest.TestCase):
    """Test cases for ReppiScraper."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.scraper = ReppiScraper(max_retries=1, retry_delay=0.1)
    
    def test_parse_date_iso(self):
        """Test ISO date parsing."""
        result = self.scraper._parse_date("2026-06-11")
        self.assertEqual(result, datetime(2026, 6, 11))
    
    def test_parse_date_finnish(self):
        """Test Finnish date parsing."""
        result = self.scraper._parse_finnish_date("5. kesäkuuta 2026")
        self.assertEqual(result, datetime(2026, 6, 5))
    
    def test_parse_date_finnish_short_month(self):
        """Test Finnish date parsing with short month name."""
        result = self.scraper._parse_finnish_date("15. maalis 2026")
        self.assertEqual(result, datetime(2026, 3, 15))
    
    def test_extract_date_range(self):
        """Test date range extraction."""
        start, end = self.scraper._extract_date_range("5.–7. kesäkuuta 2026")
        self.assertEqual(start, datetime(2026, 6, 5))
        self.assertEqual(end, datetime(2026, 6, 7))
    
    def test_classify_level_elite(self):
        """Test elite level classification."""
        level = self.scraper._classify_level("CrossFit Games 2026")
        self.assertEqual(level, CompetitionLevel.ELITE)
        
        level = self.scraper._classify_level("SM-kisat Turku")
        self.assertEqual(level, CompetitionLevel.ELITE)
        
        level = self.scraper._classify_level("Unbroken Finaalit")
        self.assertEqual(level, CompetitionLevel.ELITE)
    
    def test_classify_level_hobby(self):
        """Test hobby level classification."""
        level = self.scraper._classify_level("Harrastesarja")
        self.assertEqual(level, CompetitionLevel.HOBBY)
        
        level = self.scraper._classify_level("Kuntosarja kisa")
        self.assertEqual(level, CompetitionLevel.HOBBY)
    
    def test_classify_level_unknown(self):
        """Test unknown level classification."""
        level = self.scraper._classify_level("Random Competition")
        self.assertEqual(level, CompetitionLevel.UNKNOWN)
    
    def test_parse_api_item(self):
        """Test API item parsing."""
        item = {
            "name": "Test Competition",
            "startDate": "2026-06-11",
            "endDate": "2026-06-13",
            "location": "Helsinki",
            "description": "Test description",
            "url": "/events/123"
        }
        
        comp = self.scraper._parse_api_item(item)
        
        self.assertIsNotNone(comp)
        self.assertEqual(comp.name, "Test Competition")
        self.assertEqual(comp.date_start, datetime(2026, 6, 11))
        self.assertEqual(comp.date_end, datetime(2026, 6, 13))
        self.assertEqual(comp.location, "Helsinki")
        self.assertEqual(comp.description, "Test description")
        self.assertEqual(comp.info_url, "https://reppi.fi/events/123")
    
    def test_parse_api_item_no_name(self):
        """Test API item parsing with no name."""
        item = {
            "startDate": "2026-06-11",
            "location": "Helsinki"
        }
        
        comp = self.scraper._parse_api_item(item)
        self.assertIsNone(comp)
    
    def test_fallback_competitions(self):
        """Test fallback competitions."""
        comps = self.scraper._get_fallback_competitions()
        
        self.assertGreater(len(comps), 0)
        
        # Check that we have expected competitions
        names = [c.name for c in comps]
        self.assertIn("Turku Tuomiopäivä", names)
        self.assertIn("Yyteri Sandstorm", names)
    
    @patch('reppi_scraper.requests.Session')
    def test_fetch_from_api_success(self, mock_session):
        """Test successful API fetch."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'Content-Type': 'application/json'}
        mock_response.json.return_value = [
            {
                "name": "API Test Competition",
                "startDate": "2026-07-01",
                "location": "Tampere"
            }
        ]
        
        mock_session_instance = Mock()
        mock_session_instance.get.return_value = mock_response
        mock_session.return_value = mock_session_instance
        
        # Re-initialize scraper with mocked session
        self.scraper.session = mock_session_instance
        
        comps = self.scraper._fetch_from_api()
        
        self.assertEqual(len(comps), 1)
        self.assertEqual(comps[0].name, "API Test Competition")
    
    @patch('reppi_scraper.requests.Session')
    def test_fetch_from_api_failure(self, mock_session):
        """Test API fetch failure."""
        mock_session_instance = Mock()
        mock_session_instance.get.side_effect = Exception("Connection error")
        mock_session.return_value = mock_session_instance
        
        self.scraper.session = mock_session_instance
        
        comps = self.scraper._fetch_from_api()
        
        self.assertEqual(len(comps), 0)
    
    def test_competition_dataclass(self):
        """Test Competition dataclass."""
        comp = Competition(
            name="Test",
            date_start=datetime(2026, 6, 11),
            date_end=None,
            location="Helsinki",
            country="Finland",
            level=CompetitionLevel.ELITE
        )
        
        self.assertEqual(comp.name, "Test")
        self.assertEqual(comp.categories, [])  # Default value


class TestReppiScraperIntegration(unittest.TestCase):
    """Integration tests - these make real network calls."""
    
    def test_fetch_competitions_returns_data(self):
        """Test that fetch_competitions returns data."""
        scraper = ReppiScraper(max_retries=1, retry_delay=0.1)
        competitions = scraper.fetch_competitions()
        
        # Should return at least fallback competitions
        self.assertGreater(len(competitions), 0)
        
        # Check that competitions have required fields
        for comp in competitions:
            self.assertIsNotNone(comp.name)
            self.assertIn(comp.level, [CompetitionLevel.ELITE, CompetitionLevel.HOBBY, CompetitionLevel.UNKNOWN])
    
    def test_fetch_competition_details_structure(self):
        """Test that fetch_competition_details returns expected structure."""
        scraper = ReppiScraper(max_retries=1, retry_delay=0.1)
        
        # Use a known URL
        details = scraper.fetch_competition_details("https://reppi.fi/events")
        
        # Check structure
        self.assertIn('url', details)
        self.assertIn('description', details)
        self.assertIn('registration_end', details)
        self.assertIn('price', details)
        self.assertIn('youtube_link', details)
        self.assertIn('categories', details)
        self.assertIn('venue', details)


def run_tests():
    """Run all tests."""
    # Run unit tests
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add unit tests
    suite.addTests(loader.loadTestsFromTestCase(TestReppiScraper))
    
    # Add integration tests (comment out to skip network calls)
    suite.addTests(loader.loadTestsFromTestCase(TestReppiScraperIntegration))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)

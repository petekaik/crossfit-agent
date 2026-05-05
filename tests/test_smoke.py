#!/usr/bin/env python3
"""Quick smoke test for cron_runner"""

import sys
import subprocess
from pathlib import Path

WORKSPACE = Path("/Users/petekaik/projects/crossfit-agent")

# Test 1: Check Python can import modules
def test_imports():
    """Test that modules can be imported."""
    print("Test 1: Testing imports...")
    
    # Add src to path
    sys.path.insert(0, str(WORKSPACE / "src"))
    
    try:
        from scraper import CompetitionAggregator
        print("  ✓ CompetitionAggregator imported")
    except Exception as e:
        print(f"  ✗ Failed to import CompetitionAggregator: {e}")
        return False
    
    try:
        from reppi_scraper import ReppiScraper
        print("  ✓ ReppiScraper imported")
    except Exception as e:
        print(f"  ✗ Failed to import ReppiScraper: {e}")
        return False
    
    try:
        from calendar_sync import GoogleCalendarSync
        print("  ✓ GoogleCalendarSync imported")
    except Exception as e:
        print(f"  ✗ Failed to import GoogleCalendarSync: {e}")
        return False
    
    return True


# Test 2: Test ReppiScraper initialization
def test_reppi_scraper():
    """Test ReppiScraper can be initialized."""
    print("\nTest 2: Testing ReppiScraper...")
    
    sys.path.insert(0, str(WORKSPACE / "src"))
    from reppi_scraper import ReppiScraper
    
    try:
        scraper = ReppiScraper(max_retries=1, retry_delay=0.1)
        print("  ✓ ReppiScraper initialized")
        
        # Test fallback
        comps = scraper._get_fallback_competitions()
        print(f"  ✓ Fallback competitions: {len(comps)}")
        
        return True
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False


# Test 3: Test subprocess execution
def test_subprocess():
    """Test subprocess can run."""
    print("\nTest 3: Testing subprocess execution...")
    
    import os
    env = os.environ.copy()
    env["PYTHONPATH"] = str(WORKSPACE / "src")
    
    result = subprocess.run(
        [sys.executable, "-c", "from scraper import CompetitionAggregator; print('OK')"],
        cwd=WORKSPACE,
        capture_output=True,
        text=True,
        env=env
    )
    
    if result.returncode == 0 and "OK" in result.stdout:
        print("  ✓ Subprocess with PYTHONPATH works")
        return True
    else:
        print(f"  ✗ Failed: {result.stderr}")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("Smoke Tests for CrossFit Cron Runner")
    print("=" * 50)
    print()
    
    results = []
    results.append(("Imports", test_imports()))
    results.append(("ReppiScraper", test_reppi_scraper()))
    results.append(("Subprocess", test_subprocess()))
    
    print()
    print("=" * 50)
    print("Results:")
    print("=" * 50)
    
    all_passed = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print("✓ All smoke tests passed!")
        sys.exit(0)
    else:
        print("✗ Some tests failed")
        sys.exit(1)

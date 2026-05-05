#!/usr/bin/env python3
"""
CrossFit Competition Tracker - Enhanced Cron Wrapper

Advanced error handling, logging, and fault tolerance.
"""

import json
import logging
import os
import subprocess
import sys
import traceback
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Setup paths
WORKSPACE = Path("/Users/petekaik/.openclaw/workspace/projects/crossfit-agent")
LOG_DIR = WORKSPACE / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

STATE_FILE = WORKSPACE / "data" / "cron_state.json"
ERROR_LOG_FILE = WORKSPACE / "data" / "error_log.json"
ALERT_CONFIG_FILE = WORKSPACE / "data" / "alert_config.json"


class ErrorCategory(Enum):
    """Error categories for better analysis."""
    NETWORK = "network"          # Connection timeouts, DNS failures
    API = "api"                    # API errors, rate limiting
    PARSING = "parsing"            # HTML/JSON parsing errors
    AUTH = "auth"                  # Authentication failures
    CONFIG = "config"              # Missing configuration
    DEPENDENCY = "dependency"      # Missing modules, Playwright issues
    UNKNOWN = "unknown"            # Uncategorized errors


class ErrorSeverity(Enum):
    """Error severity levels."""
    INFO = "info"                  # Informational, no action needed
    WARNING = "warning"            # Warning, monitoring recommended
    ERROR = "error"                # Error, requires attention
    CRITICAL = "critical"          # Critical, immediate action required


class CircuitBreaker:
    """Circuit breaker pattern to prevent repeated failures."""
    
    def __init__(self, failure_threshold: int = 3, recovery_timeout: int = 300):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def record_success(self):
        """Record a successful operation."""
        self.failures = 0
        self.state = "CLOSED"
    
    def record_failure(self):
        """Record a failed operation."""
        self.failures += 1
        self.last_failure_time = datetime.now()
        
        if self.failures >= self.failure_threshold:
            self.state = "OPEN"
    
    def can_execute(self) -> bool:
        """Check if operation can be executed."""
        if self.state == "CLOSED":
            return True
        
        if self.state == "OPEN":
            # Check if recovery timeout has passed
            if self.last_failure_time:
                elapsed = (datetime.now() - self.last_failure_time).total_seconds()
                if elapsed > self.recovery_timeout:
                    self.state = "HALF_OPEN"
                    return True
            return False
        
        return True  # HALF_OPEN


class ErrorHandler:
    """Centralized error handling and logging."""
    
    def __init__(self):
        self.error_history = self._load_error_log()
        self.circuit_breakers = {}
    
    def _load_error_log(self) -> List[Dict]:
        """Load error log from file."""
        if ERROR_LOG_FILE.exists():
            with open(ERROR_LOG_FILE) as f:
                return json.load(f)
        return []
    
    def _save_error_log(self):
        """Save error log to file."""
        # Keep only last 100 errors
        trimmed_errors = self.error_history[-100:]
        with open(ERROR_LOG_FILE, 'w') as f:
            json.dump(trimmed_errors, f, indent=2, default=str)
    
    def categorize_error(self, error_msg: str) -> Tuple[ErrorCategory, ErrorSeverity]:
        """Categorize error based on message."""
        error_lower = error_msg.lower()
        
        # Network errors
        if any(kw in error_lower for kw in ['timeout', 'connection', 'dns', 'network', 'unreachable']):
            return ErrorCategory.NETWORK, ErrorSeverity.ERROR
        
        # API errors
        if any(kw in error_lower for kw in ['api', 'rate limit', '429', '403', '401', '500', '503']):
            return ErrorCategory.API, ErrorSeverity.ERROR
        
        # Parsing errors
        if any(kw in error_lower for kw in ['parse', 'json', 'html', 'decode', 'invalid']):
            return ErrorCategory.PARSING, ErrorSeverity.WARNING
        
        # Auth errors
        if any(kw in error_lower for kw in ['auth', 'token', 'credential', 'permission']):
            return ErrorCategory.AUTH, ErrorSeverity.CRITICAL
        
        # Config errors
        if any(kw in error_lower for kw in ['config', 'missing', 'not found', 'file']):
            return ErrorCategory.CONFIG, ErrorSeverity.ERROR
        
        # Dependency errors
        if any(kw in error_lower for kw in ['module', 'import', 'playwright', 'no module']):
            return ErrorCategory.DEPENDENCY, ErrorSeverity.ERROR
        
        return ErrorCategory.UNKNOWN, ErrorSeverity.WARNING
    
    def log_error(self, operation: str, error_msg: str, traceback_str: Optional[str] = None):
        """Log an error with full context."""
        category, severity = self.categorize_error(error_msg)
        
        error_entry = {
            'timestamp': datetime.now().isoformat(),
            'operation': operation,
            'message': error_msg,
            'category': category.value,
            'severity': severity.value,
            'traceback': traceback_str
        }
        
        self.error_history.append(error_entry)
        self._save_error_log()
        
        return error_entry
    
    def get_circuit_breaker(self, operation: str) -> CircuitBreaker:
        """Get or create circuit breaker for operation."""
        if operation not in self.circuit_breakers:
            self.circuit_breakers[operation] = CircuitBreaker()
        return self.circuit_breakers[operation]
    
    def should_alert(self, operation: str) -> Tuple[bool, str]:
        """Check if alert should be sent for repeated failures."""
        # Get recent errors for this operation
        recent_errors = [
            e for e in self.error_history[-10:]
            if e['operation'] == operation
        ]
        
        if len(recent_errors) >= 3:
            # Check if last 3 were consecutive failures
            return True, f"3 consecutive failures in {operation}"
        
        # Check for critical errors
        critical_count = sum(
            1 for e in self.error_history[-24:]
            if e['operation'] == operation and e['severity'] == 'critical'
        )
        
        if critical_count > 0:
            return True, f"Critical error detected in {operation}"
        
        return False, ""
    
    def get_error_summary(self, hours: int = 24) -> Dict:
        """Get error summary for time period."""
        cutoff = datetime.now() - timedelta(hours=hours)
        
        recent_errors = [
            e for e in self.error_history
            if datetime.fromisoformat(e['timestamp']) > cutoff
        ]
        
        summary = {
            'total': len(recent_errors),
            'by_category': {},
            'by_severity': {},
            'by_operation': {}
        }
        
        for error in recent_errors:
            cat = error['category']
            sev = error['severity']
            op = error['operation']
            
            summary['by_category'][cat] = summary['by_category'].get(cat, 0) + 1
            summary['by_severity'][sev] = summary['by_severity'].get(sev, 0) + 1
            summary['by_operation'][op] = summary['by_operation'].get(op, 0) + 1
        
        return summary


# Global error handler
error_handler = ErrorHandler()


def setup_logging():
    """Setup logging with rotation."""
    log_file = LOG_DIR / f"cron_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)


def load_state() -> dict:
    """Load cron state."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        'last_run': None,
        'last_success': None,
        'total_runs': 0,
        'success_count': 0,
        'fail_count': 0,
        'consecutive_failures': 0
    }


def save_state(state: dict):
    """Save cron state."""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)


def run_command_with_env(cmd: list, env: dict, timeout: int = 300, 
                         operation: str = "unknown") -> Tuple[bool, str]:
    """Run command with custom environment, timeout, and error handling."""
    logger = logging.getLogger(__name__)
    
    # Check circuit breaker
    cb = error_handler.get_circuit_breaker(operation)
    if not cb.can_execute():
        logger.warning(f"Circuit breaker OPEN for {operation}, skipping execution")
        return False, f"Circuit breaker open for {operation}"
    
    try:
        full_env = os.environ.copy()
        full_env.update(env)
        
        logger.info(f"Running command: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=full_env
        )
        
        if result.returncode == 0:
            cb.record_success()
            return True, result.stdout
        else:
            error_msg = f"Exit code: {result.returncode}"
            if result.stderr:
                error_msg += f"\nSTDERR: {result.stderr}"
            
            cb.record_failure()
            error_handler.log_error(operation, error_msg)
            return False, error_msg
            
    except subprocess.TimeoutExpired:
        error_msg = f"Command timed out after {timeout} seconds"
        cb.record_failure()
        error_handler.log_error(operation, error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"Exception: {str(e)}"
        tb = traceback.format_exc()
        cb.record_failure()
        error_handler.log_error(operation, error_msg, tb)
        return False, error_msg


def run_with_retry(operation: str, cmd: list, env: dict, 
                   max_retries: int = 3, timeout: int = 300) -> Tuple[bool, str]:
    """Run command with retry logic."""
    logger = logging.getLogger(__name__)
    
    for attempt in range(max_retries):
        if attempt > 0:
            delay = 2 ** attempt  # Exponential backoff
            logger.info(f"Retry attempt {attempt}/{max_retries} after {delay}s delay...")
            import time
            time.sleep(delay)
        
        success, output = run_command_with_env(cmd, env, timeout, operation)
        
        if success:
            return True, output
        
        # Check if error is retryable
        error_entry = error_handler.error_history[-1] if error_handler.error_history else None
        if error_entry:
            category = error_entry.get('category')
            if category in ['auth', 'config']:
                logger.error(f"Non-retryable error: {category}")
                return False, output
    
    return False, output


def run_search() -> bool:
    """Run competition search with enhanced error handling."""
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("Starting competition search (ReppiScraper)")
    logger.info("=" * 60)
    
    cmd = [sys.executable, "src/main.py", "search"]
    env = {"PYTHONPATH": str(WORKSPACE / "src")}
    
    success, output = run_with_retry("search", cmd, env, max_retries=3, timeout=300)
    
    if output:
        logger.info(output)
    
    if success:
        logger.info("✓ Search completed successfully")
    else:
        logger.error("✗ Search failed after all retries")
    
    return success


def run_sync() -> bool:
    """Run calendar sync with enhanced error handling."""
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("Starting calendar sync")
    logger.info("=" * 60)
    
    cmd = [sys.executable, "src/main.py", "sync"]
    env = {"PYTHONPATH": str(WORKSPACE / "src")}
    
    # Sync is less critical, try only once
    success, output = run_command_with_env(cmd, env, timeout=300, operation="sync")
    
    if output:
        logger.info(output)
    
    if success:
        logger.info("✓ Sync completed successfully")
    else:
        logger.error("✗ Sync failed")
    
    return success


def run_full() -> bool:
    """Run full pipeline with enhanced error handling."""
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("Starting full pipeline")
    logger.info("=" * 60)
    
    search_success = run_search()
    
    if not search_success:
        logger.warning("Search failed, attempting sync anyway...")
    
    sync_success = run_sync()
    
    return search_success and sync_success


def check_alerts() -> List[Tuple[str, str]]:
    """Check for alerts to send."""
    alerts = []
    
    for operation in ['search', 'sync']:
        should_alert, message = error_handler.should_alert(operation)
        if should_alert:
            alerts.append((operation, message))
    
    return alerts


def main():
    """Main entry point with enhanced error handling."""
    import argparse
    
    parser = argparse.ArgumentParser(description="CrossFit Enhanced Cron Wrapper")
    parser.add_argument(
        'command',
        choices=['search', 'sync', 'full', 'status', 'errors'],
        help='Command to run'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging()
    
    # Special commands
    if args.command == 'status':
        state = load_state()
        print("=" * 60)
        print("CrossFit Tracker Status")
        print("=" * 60)
        print(f"Last run: {state.get('last_run', 'Never')}")
        print(f"Last success: {state.get('last_success', 'Never')}")
        print(f"Total runs: {state.get('total_runs', 0)}")
        print(f"Success count: {state.get('success_count', 0)}")
        print(f"Fail count: {state.get('fail_count', 0)}")
        print(f"Consecutive failures: {state.get('consecutive_failures', 0)}")
        print()
        print("Recent errors (last 24h):")
        summary = error_handler.get_error_summary(24)
        print(f"  Total: {summary['total']}")
        if summary['by_category']:
            for cat, count in summary['by_category'].items():
                print(f"  - {cat}: {count}")
        return 0
    
    if args.command == 'errors':
        print("=" * 60)
        print("Error Log (last 10)")
        print("=" * 60)
        for error in error_handler.error_history[-10:]:
            print(f"\n[{error['timestamp']}] {error['operation']}")
            print(f"  Category: {error['category']} | Severity: {error['severity']}")
            print(f"  Message: {error['message'][:100]}...")
        return 0
    
    # Load state
    state = load_state()
    state['last_run'] = datetime.now().isoformat()
    state['total_runs'] += 1
    
    logger.info(f"Cron job started: {args.command}")
    logger.info(f"Workspace: {WORKSPACE}")
    
    # Run command
    if args.command == 'search':
        success = run_search()
    elif args.command == 'sync':
        success = run_sync()
    elif args.command == 'full':
        success = run_full()
    else:
        logger.error(f"Unknown command: {args.command}")
        return 1
    
    # Update state
    if success:
        state['last_success'] = datetime.now().isoformat()
        state['success_count'] += 1
        state['consecutive_failures'] = 0
    else:
        state['fail_count'] += 1
        state['consecutive_failures'] += 1
    
    save_state(state)
    
    # Check for alerts
    alerts = check_alerts()
    if alerts:
        logger.warning("=" * 60)
        logger.warning("ALERTS DETECTED:")
        for operation, message in alerts:
            logger.warning(f"  [{operation}] {message}")
        logger.warning("=" * 60)
    
    # Summary
    logger.info("=" * 60)
    logger.info(f"Cron job completed: {args.command}")
    logger.info(f"Success: {success}")
    logger.info(f"Total runs: {state['total_runs']}")
    logger.info(f"Success count: {state['success_count']}")
    logger.info(f"Fail count: {state['fail_count']}")
    logger.info(f"Consecutive failures: {state['consecutive_failures']}")
    logger.info("=" * 60)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

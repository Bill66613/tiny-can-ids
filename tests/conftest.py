# conftest.py
import time
import pytest

# A global variable to store the start time.
_session_start_time = 0

def pytest_sessionstart(session):
    """Called upon at the start of a test run."""
    global _session_start_time
    _session_start_time = time.time()

def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """The dashboard summarizes the results after the test is completed."""
    stats = terminalreporter.stats
    passed = len(stats.get('passed', []))
    failed = len(stats.get('failed', []))
    skipped = len(stats.get('skipped', []))
    
    # Calculate the time based on the stored global variable.
    duration_seconds = time.time() - _session_start_time

    print("\n" + "="*50)
    print("      TINY-CAN-IDS AUTOMATION SUMMARY")
    print("="*50)
    print(f" Status:   {'PASSED' if exitstatus == 0 else 'FAILED'}")
    print(f" Total:    {passed + failed + skipped}")
    print(f" Passed:   {passed}")
    print(f" Failed:   {failed}")
    print(f" Time:     {duration_seconds:.2f}s")
    print("="*50)
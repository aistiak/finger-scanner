"""RTMS Biometric System — application entry point."""
import multiprocessing
import sys

if getattr(sys, "frozen", False):
    multiprocessing.freeze_support()

from lib import run_app


if __name__ == "__main__":
    # Frozen exe re-spawns workers; only the main process starts the GUI.
    if multiprocessing.current_process().name != "MainProcess":
        sys.exit(0)
    run_app()

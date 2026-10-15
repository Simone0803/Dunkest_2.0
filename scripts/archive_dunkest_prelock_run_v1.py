#!/usr/bin/env python3
"""Compatibility entry point for the canonical immutable pre-lock archiver.

Use archive_dunkest_pre_lock_run_v1.py as the single source of truth. The old
no-underscore implementation wrote an incompatible archive layout that could
not be consumed by the integrity reviewer and post-match evaluation pipeline.
"""
from __future__ import annotations

from archive_dunkest_pre_lock_run_v1 import main

if __name__ == "__main__":
    main()

"""Shared versioned paths; choose a completed replay with NYGRID_REPAIR_RUN_LABEL."""
from pathlib import Path
import os
import re

ROOT=Path(__file__).resolve().parents[4]
REPAIR=ROOT/'output/nygrid_2025_physical_repair'
DELIVERY=REPAIR/'delivery'
RUN_LABEL=os.environ.get('NYGRID_REPAIR_RUN_LABEL','physical_repair_v1')
assert re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}',RUN_LABEL),RUN_LABEL
ANNUAL=REPAIR/'annual'/RUN_LABEL
COMPARISON=ANNUAL/'comparison'
OUT=DELIVERY/'map'

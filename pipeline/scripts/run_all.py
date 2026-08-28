"""
Runs the full election-modelling pipeline in order:

  1. allocate_tribes   -> split raw party votes into voter "tribes"
  2. project_flows     -> apply tribe transition matrices, project new vote shares
  4. tactical_voting   -> squeeze non-winnable parties' votes to a winnable alternative
                           (winnable = incumbent, projected leader, or within 10pts of the leader)
  5. export_svg_output -> apply local adjustments, write final results for the map

Usage:
    py run_all.py
"""
import runpy
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent

STAGES = [
    "01_allocate_tribes.py",
    "02_project_flows.py",
    "04_tactical_voting.py",
    "05_export_svg_output.py",
]

for stage in STAGES:
    print(f"=== Running {stage} ===")
    runpy.run_path(str(SCRIPTS_DIR / stage), run_name="__main__")

print("Pipeline complete.")

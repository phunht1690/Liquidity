"""Absolute-path entry point for current-user Windows logon."""
from pathlib import Path
import os
import sys

project=Path(__file__).resolve().parents[1]
os.chdir(project)
sys.path.insert(0,str(project))
from src.app.background import main

if __name__=='__main__':raise SystemExit(main())

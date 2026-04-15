"""
Test bootstrap.

`aws-profile-switcher.py` has a hyphen in its filename, which isn't a valid
Python identifier. Load it manually via importlib so tests can simply do:

    import aws_profile_switcher as aps
"""

import importlib.util
import sys
from pathlib import Path

_ROOT   = Path(__file__).resolve().parent.parent
_SCRIPT = _ROOT / "aws-profile-switcher.py"

_spec   = importlib.util.spec_from_file_location("aws_profile_switcher", _SCRIPT)
_module = importlib.util.module_from_spec(_spec)
sys.modules["aws_profile_switcher"] = _module
_spec.loader.exec_module(_module)
"""Compatibility shim for historical imports.

Authoritative AC sizing rules now live in `calb_sizing_tool.services.ac_sizing_service`.
"""

from calb_sizing_tool.services.ac_sizing_service import *  # noqa: F401,F403

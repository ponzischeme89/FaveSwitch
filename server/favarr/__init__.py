"""
Favarr server package.

Holds shared extensions and models so they can be imported across modules
without creating circular dependencies.
"""

from .extensions import db  # noqa: F401

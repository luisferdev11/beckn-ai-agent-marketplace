"""
Shared rate limiter — used by POST /api/plan to prevent abuse.

The limiter must be a single module-level instance so the slowapi decorator
sees the same object when routes are imported and when main.py wires the
exception handler. Do not instantiate Limiter elsewhere.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

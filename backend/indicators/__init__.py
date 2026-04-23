"""
System-wide technical indicators.

Indicators are pure, stateless functions that take a DataFrame and return
a DataFrame with additional columns appended. They have no side effects
(no DB writes, no logging, no config lookups).

Callers are responsible for caching, persistence, and side effects.
"""

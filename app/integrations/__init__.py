"""External system integrations.

Each integration is read-only — the POC consumes data from systems of record
(SmartLinx for scheduling, Kronos-style time clocks for hours) but never
writes back. Source-of-truth ownership stays with the client's existing tools.
"""

from __future__ import annotations


class AppError(Exception):
    """Base application error."""

    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class UnitNotFoundError(AppError):
    def __init__(self, unit_id: str):
        super().__init__(f"Unit not found: {unit_id}", status_code=404)


class CalloutNotFoundError(AppError):
    def __init__(self, callout_id: str):
        super().__init__(f"Callout not found: {callout_id}", status_code=404)


class NoCandidatesError(AppError):
    def __init__(self, unit_id: str, shift_label: str):
        super().__init__(
            f"No eligible candidates found for unit {unit_id}, shift {shift_label}",
            status_code=200,
        )

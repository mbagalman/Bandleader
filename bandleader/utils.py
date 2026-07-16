import logging
import sys
from dataclasses import dataclass


def setup_logging(verbose: bool = False) -> None:
    """Configure standard logging for the application."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(message)s",
        stream=sys.stderr,
    )


@dataclass(frozen=True)
class TimeSignature:
    """Time signature representation (e.g., 4/4, 3/4, 6/8)."""

    numerator: int
    denominator: int = 4

    @property
    def beats_per_bar(self) -> float:
        """Quarter-note beats per bar."""
        if self.numerator <= 0 or self.denominator <= 0:
            raise ValueError("Time signature values must be positive.")
        return self.numerator * (4.0 / self.denominator)

    @property
    def steps_per_bar(self) -> int:
        """16th-note steps per bar."""
        return max(1, int(round(self.numerator * 16.0 / self.denominator)))

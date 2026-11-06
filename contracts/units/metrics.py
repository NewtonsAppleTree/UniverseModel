"""Canonical metric unit tokens; this is a vocabulary, not a dimensional expression engine."""


METRIC_UNITS = frozenset({  # Supported unit IDs; display prefixes/bit-byte conversions are explicit producer operations.
    "one", "bit", "byte", "second", "hertz", "joule", "watt", "square_millimeter", "kelvin",
    "volt", "ampere", "siemens", "ohm", "cycle", "MAC", "FLOP", "operation", "conversion",
    "cell_evaluation", "sample", "request", "token", "byte_per_second", "bit_per_second",
    "operation_per_second", "token_per_second", "joule_per_token",
})


# Validate canonical unit identity; reject ns/GB/s aliases so scale factors cannot disappear at a boundary.
def validate_metric_unit(unit: str) -> None:
    if type(unit) is not str or unit not in METRIC_UNITS:
        raise ValueError(f"unsupported metric unit: {unit}; use a canonical unit token")

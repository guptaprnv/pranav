"""Version tags for each primitive's computation method.

Centralized so a formula change is a one-line bump here, not a hunt through
the primitive modules -- and so a stored PrimitiveResult can always say
exactly which version of which formula produced it, per
docs/engineering/data-architecture.md ("pipeline version" as a first-class
schema field, distinct from the input data's own as-of date).
"""

RETURNS_V1 = "returns_v1"
ALPHA_BETA_V1 = "alpha_beta_v1"
VAR_HISTORICAL_V1 = "var_historical_v1"
CORRELATION_V1 = "correlation_v1"
DRIFT_V1 = "drift_v1"
CONCENTRATION_V1 = "concentration_v1"

"""Every threshold the Insight Engine uses, in one place."""

# Ranking: rank = severity weight × (1 + impact), impact being 0 to 10 and set by each rule.
# The weights keep the bands apart: the lowest critical (1,000) outranks the highest warning (550),
# and the lowest warning (50) outranks the highest info (44).
SEVERITY_WEIGHT = {"critical": 1000, "warning": 50, "info": 4}
IMPACT_CAP = 10.0

# At-risk dispatches
CRITICAL_LATE_WORKING_DAYS = 3
WORST_LINES = 3  # lines that also get a card of their own
LISTED_LINES = 10  # lines named on the summary card

# Bottleneck forecast and capacity gaps (utilisation as a share of capacity)
HOT_UTIL = 0.85
SATURATED_UTIL = 0.999
SATURATED_DAYS_CRITICAL = 3
GAP_CRITICAL_SHARE = 0.25  # a weekly shortfall of this share of capacity is critical
SPARE_UTIL = 0.5
MAX_SPARE_CARDS = 3

# Melting
UNEVEN_CV = 0.35  # standard deviation over mean of daily furnace utilisation
UNEVEN_LOW = 0.4
UNEVEN_MIN_DAYS = 4
MELT_DAYS_LISTED = 28

# Load balancing
MAX_BALANCE_CARDS = 3
BALANCE_MIN_GAP = 0.25  # the alternative must be this much less loaded than the overloaded resource

# Dispatch performance (on time = actual date on or before the internal date)
ON_TIME_WARN = 0.8
ON_TIME_CRITICAL = 0.6
REPEAT_MIN_LINES = 3
REPEAT_ON_TIME = 0.7
MAX_REPEAT_CARDS = 3

# Month-end forecast
MONTH_SHORT_CRITICAL = 0.15
SLIPPING_LISTED = 10

# Concentration and mix
CONCENTRATION_TOP_N = 3
CONCENTRATION_WARN_SHARE = 0.5
LARGE_FACTOR = 3.0  # a line this many times the part's usual quantity is unusual
LARGE_MIN_HISTORY = 3
MAX_LARGE_CARDS = 3

# Trends, digest, history
TREND_MIN_CHANGE = 0.1
DIGEST_SIZE = 5
RUNS_KEPT = 60

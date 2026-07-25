"""Model constants: park factors, stadium orientations, weights.

Park factors are 3-year runs park factors in the style FanGraphs/Savant
publish (100 = neutral). Editable — keyed by MLB venue id.
CF_BEARING = compass bearing from home plate toward center field, used to
decompose wind into blowing-out / blowing-in components.
"""

# venue_id: (park_factor_runs, cf_bearing_deg)
PARKS = {
    3:    (108, 52),   # Fenway Park
    3313: (102, 75),   # Yankee Stadium
    5:    (98,  0),    # Progressive Field
    4705: (100, 35),   # Truist Park
    14:   (98,  0),    # Rogers Centre (retractable)
    32:   (98, 130),   # American Family Field (retractable)
    17:   (102, 45),   # Wrigley Field
    2392: (99,  345),  # Daikin Park (retractable)
    7:    (104, 45),   # Kauffman Stadium
    19:   (113, 3),    # Coors Field
    1:    (101, 65),   # Angel Stadium
    2529: (104, 40),   # Sutter Health Park (Athletics)
    15:   (103, 0),    # Chase Field (retractable)
    680:  (94,  49),   # T-Mobile Park (retractable)
    2:    (101, 31),   # Oriole Park at Camden Yards
    2394: (98,  95),   # Comerica Park
    22:   (99,  26),   # Dodger Stadium
    2395: (96,  85),   # Oracle Park
    2680: (96,  0),    # Petco Park
    4169: (97,  40),   # loanDepot park (retractable)
    3289: (96,  15),   # Citi Field
    2681: (102, 10),   # Citizens Bank Park
    31:   (98,  25),   # PNC Park
    2889: (100, 62),   # Busch Stadium
    2602: (104, 120),  # Great American Ball Park
    3309: (101, 28),   # Nationals Park
    3312: (98,  90),   # Target Field
    5325: (100, 0),    # Globe Life Field (retractable)
    4:    (102, 27),   # Rate Field (White Sox)
    2523: (104, 45),   # George M. Steinbrenner Field (Rays)
}

DEFAULT_PARK_FACTOR = 100
DEFAULT_CF_BEARING = 45

LEAGUE = {
    "home_win_pct": 0.540,
    "woba": 0.310,
    "ops": 0.715,
    "fip_constant": 3.15,
    "avg_fip": 4.20,
    "hr_per_pa": 0.031,
    "pyth_exponent": 1.83,
}

# Factor weights: multipliers on each factor's raw log-odds edge, with caps.
WEIGHTS = {
    "season":     dict(w=0.55, cap=0.60),
    "home_away":  dict(w=0.35, cap=0.30, base_hfa=0.16),
    "pitching":   dict(w=0.27, cap=0.50),
    "bvp":        dict(w=0.90, cap=0.25),
    "arsenal":    dict(w=3.20, cap=0.35),
    "weather":    dict(w=1.00, cap=0.12),
    "day_night":  dict(w=0.25, cap=0.10),
    "park":       dict(w=1.00, cap=0.10),
    "injuries":   dict(w=1.00, cap=0.25),
}

# Multiplies the final summed log-odds. Lower toward ~0.75 if the pick log
# shows systematic overconfidence (needs a few hundred settled picks).
GLOBAL_SHRINK = 1.0

SHRINK = {
    "team_wpct_games": 16,
    "bvp_pa": 70,
}

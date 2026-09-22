"""Weekly WPSR sulfur series. Above 15 ppm combines both published high bands."""

REGIONS = {
    "I": ("R10", "P11", "P12"),
    "A": ("R1X", "1A1", None),
    "B": ("R1Y", "1B1", None),
    "C": ("R1Z", "1C1", None),
    "II": ("R20", "P21", "P22"),
    "III": ("R30", "P31", "P32"),
    "IV": ("R40", "P41", "P42"),
    "V": ("R50", "P51", "P52"),
    "TOT": ("NUS", "US1", "US2"),
}


def sulfur_sources(metric: str, band: str, region: str) -> tuple[str, ...]:
    area, stock_suffix, production_suffix = REGIONS[region]
    if metric == "stocks":
        if band == "low":
            return (f"WD0ST_{area}_1",)
        return (f"WD1ST_{area}_1", f"WDGST{stock_suffix}")
    if metric == "production" and production_suffix is not None:
        if band == "low":
            return (f"WD0TP_{area}_2",)
        return (f"WD1TP_{area}_2", f"WDGRP{production_suffix}")
    raise ValueError(f"Weekly sulfur {metric} is not published for {region}")

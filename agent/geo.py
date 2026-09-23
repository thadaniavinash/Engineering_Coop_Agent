"""Location parsing and straight-line distance from home (Newmarket by default).

No external geocoding service is used (free, no API key, no rate limits).
Coordinates are approximate town centres, accurate to within a few km, which is
fine for ranking. Distances are straight-line; driving distance is typically ~20-30% more.
"""
from __future__ import annotations
import math
import re

# name -> (lat, lon). Keys are lower-case. Aliases map to the same point.
ONTARIO_PLACES = {
    # York Region & Simcoe (closest to Newmarket)
    "newmarket": (44.0592, -79.4613), "aurora": (44.0065, -79.4504), "east gwillimbury": (44.1000, -79.4400),
    "holland landing": (44.0990, -79.4930), "sharon": (44.1000, -79.4100), "queensville": (44.1300, -79.4200),
    "king city": (43.9280, -79.5280), "king": (43.9280, -79.5280), "nobleton": (43.8960, -79.6520), "schomberg": (44.0010, -79.6810),
    "richmond hill": (43.8828, -79.4403), "markham": (43.8561, -79.3370), "unionville": (43.8690, -79.3130),
    "vaughan": (43.8361, -79.4983), "concord": (43.8000, -79.4830), "woodbridge": (43.7830, -79.6000), "maple": (43.8530, -79.5070),
    "thornhill": (43.8150, -79.4240), "kleinburg": (43.8390, -79.6280), "stouffville": (43.9700, -79.2440),
    "whitchurch-stouffville": (43.9700, -79.2440), "georgina": (44.3000, -79.4300), "keswick": (44.2500, -79.4670),
    "sutton": (44.3000, -79.3650), "uxbridge": (44.1090, -79.1200), "bradford": (44.1150, -79.5600),
    "bradford west gwillimbury": (44.1150, -79.5600), "innisfil": (44.3000, -79.6100), "alcona": (44.3100, -79.5600),
    "barrie": (44.3894, -79.6903), "alliston": (44.1530, -79.8680), "new tecumseth": (44.1530, -79.8680),
    "tottenham": (44.0230, -79.8050), "beeton": (44.0790, -79.7820), "bolton": (43.8750, -79.7340), "caledon": (43.8600, -79.8600),
    "angus": (44.3180, -79.8830), "borden": (44.2800, -79.9100), "orillia": (44.6080, -79.4200), "midland": (44.7500, -79.8870),
    "penetanguishene": (44.7700, -79.9300), "collingwood": (44.5000, -80.2170), "wasaga beach": (44.5200, -80.0160),
    "cookstown": (44.1920, -79.7000),
    # Toronto & neighbourhoods
    "toronto": (43.6532, -79.3832), "north york": (43.7615, -79.4111), "scarborough": (43.7731, -79.2578),
    "etobicoke": (43.6205, -79.5132), "east york": (43.6910, -79.3280), "york": (43.6900, -79.4700), "downsview": (43.7450, -79.4780),
    "don mills": (43.7450, -79.3450), "rexdale": (43.7200, -79.5650), "leaside": (43.7050, -79.3650),
    # Peel & Halton
    "mississauga": (43.5890, -79.6441), "brampton": (43.7315, -79.7624), "oakville": (43.4675, -79.6877),
    "burlington": (43.3255, -79.7990), "milton": (43.5183, -79.8774), "georgetown": (43.6500, -79.9300),
    "halton hills": (43.6500, -79.9300), "acton": (43.6330, -80.0330), "malton": (43.7050, -79.6350),
    # Durham
    "pickering": (43.8384, -79.0868), "ajax": (43.8509, -79.0204), "whitby": (43.8975, -78.9429), "oshawa": (43.8971, -78.8658),
    "courtice": (43.9100, -78.7900), "bowmanville": (43.9120, -78.6870), "clarington": (43.9350, -78.6080),
    "darlington": (43.8730, -78.7200), "port perry": (44.1050, -78.9440), "scugog": (44.1050, -78.9440),
    "newcastle": (43.9170, -78.5880), "port hope": (43.9500, -78.2900), "cobourg": (43.9590, -78.1680),
    # Hamilton / Niagara
    "hamilton": (43.2557, -79.8711), "stoney creek": (43.2170, -79.7650), "ancaster": (43.2180, -79.9870),
    "dundas": (43.2670, -79.9530), "grimsby": (43.2000, -79.5660), "waterdown": (43.3350, -79.8940), "flamborough": (43.3350, -79.8940),
    "haldimand": (42.9500, -79.8700), "caledonia": (43.0730, -79.9530), "st. catharines": (43.1594, -79.2469),
    "st catharines": (43.1594, -79.2469), "niagara falls": (43.0896, -79.0849), "welland": (42.9920, -79.2480),
    "thorold": (43.1160, -79.1990), "fort erie": (42.9050, -78.9230), "port colborne": (42.8860, -79.2500),
    "niagara-on-the-lake": (43.2550, -79.0710),
    # Waterloo / Wellington / Brant
    "guelph": (43.5448, -80.2482), "kitchener": (43.4516, -80.4925), "waterloo": (43.4643, -80.5204),
    "cambridge": (43.3616, -80.3144), "brantford": (43.1394, -80.2644), "fergus": (43.7050, -80.3770),
    "elora": (43.6830, -80.4300), "orangeville": (43.9200, -80.0940), "shelburne": (44.0780, -80.2040),
    "paris": (43.1940, -80.3840), "ayr": (43.2850, -80.4500), "elmira": (43.6000, -80.5580), "stratford": (43.3700, -80.9820),
    "woodstock": (43.1306, -80.7467), "ingersoll": (43.0390, -80.8830), "tillsonburg": (42.8620, -80.7280),
    "simcoe": (42.8370, -80.3040), "listowel": (43.7350, -80.9530),
    # Southwest
    "london": (42.9849, -81.2453), "st. thomas": (42.7780, -81.1750), "st thomas": (42.7780, -81.1750),
    "windsor": (42.3149, -83.0364), "chatham": (42.4040, -82.1910), "sarnia": (42.9745, -82.4066),
    "leamington": (42.0530, -82.5990), "tecumseh": (42.3000, -82.8900), "lasalle": (42.2300, -83.0600),
    "strathroy": (42.9560, -81.6220), "goderich": (43.7430, -81.7140), "kincardine": (44.1770, -81.6360),
    "tiverton": (44.2600, -81.5400), "port elgin": (44.4370, -81.3900), "owen sound": (44.5690, -80.9430),
    "walkerton": (44.1300, -81.1500), "hanover": (44.1500, -81.0300),
    # East / Kawarthas
    "peterborough": (44.3091, -78.3197), "lindsay": (44.3560, -78.7400), "kawartha lakes": (44.3560, -78.7400),
    "belleville": (44.1628, -77.3832), "trenton": (44.1010, -77.5760), "quinte west": (44.1010, -77.5760),
    "kingston": (44.2312, -76.4860), "brockville": (44.5895, -75.6843), "cornwall": (45.0213, -74.7303),
    "napanee": (44.2490, -76.9490), "bancroft": (45.0570, -77.8540), "winchester": (45.0930, -75.3530), "hawkesbury": (45.6080, -74.6050), "picton": (44.0000, -77.1400),
    # Ottawa & north (far, but still Ontario)
    "ottawa": (45.4215, -75.6972), "kanata": (45.3088, -75.8987), "nepean": (45.3500, -75.7500), "gloucester": (45.4000, -75.6000),
    "chalk river": (46.0200, -77.4500), "pembroke": (45.8260, -77.1100), "arnprior": (45.4350, -76.3530),
    "renfrew": (45.4730, -76.6860), "north bay": (46.3091, -79.4608), "sudbury": (46.4917, -80.9930),
    "greater sudbury": (46.4917, -80.9930), "sault ste. marie": (46.5219, -84.3461), "sault ste marie": (46.5219, -84.3461),
    "timmins": (48.4758, -81.3305), "thunder bay": (48.3809, -89.2477), "huntsville": (45.3260, -79.2180),
    "bracebridge": (45.0400, -79.3100), "gravenhurst": (44.9170, -79.3730), "parry sound": (45.3440, -80.0350),
    "blind river": (46.1840, -82.9580), "elliot lake": (46.3830, -82.6500), "kapuskasing": (49.4170, -82.4330),
}

OTHER_PROVINCES = [
    "quebec", "québec", "montreal", "montréal", "laval", "longueuil", "mirabel", "saint-laurent", "dorval", "gatineau",
    "british columbia", "vancouver", "burnaby", "richmond, bc", "surrey", "victoria, bc", "delta, bc",
    "alberta", "calgary", "edmonton", "manitoba", "winnipeg", "saskatchewan", "saskatoon", "regina",
    "nova scotia", "halifax", "dartmouth", "new brunswick", "fredericton", "moncton", "saint john",
    "newfoundland", "st. john's", "prince edward island", "charlottetown", "yukon", "nunavut", "northwest territories",
]
PROVINCE_CODES = ["QC", "BC", "AB", "MB", "SK", "NS", "NB", "NL", "PE", "YT", "NU", "NT"]

US_STATE_CODES = ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA",
                  "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH",
                  "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC"]
FOREIGN_WORDS = ["united states", "usa", "u.s.", "mexico", "india", "china", "germany", "france", "united kingdom", "england",
                 "poland", "czech", "japan", "singapore", "brazil", "ireland", "netherlands", "italy", "spain", "philippines",
                 "malaysia", "hungary", "romania", "australia", "korea", "taiwan", "switzerland", "sweden", "israel",
                 "morocco", "vietnam", "thailand", "turkey", "austria", "belgium", "slovakia", "portugal", "argentina"]
# Canada ambiguities: "London" (UK), "Cambridge" (MA/UK), "Waterloo" (Belgium/IA), "Paris" (France), "Windsor" (UK)...
AMBIGUOUS = {"london", "cambridge", "waterloo", "paris", "windsor", "york", "hamilton", "kingston", "richmond hill",
             "burlington", "peterborough", "guelph", "woodstock", "stratford", "dundas", "king", "maple", "concord",
             "sharon", "sutton", "acton", "ayr", "simcoe", "picton", "delta", "milton", "georgetown", "angus", "midland",
             "newcastle", "tecumseh", "hanover", "elmira", "welland", "paris", "orangeville", "lasalle", "ancaster", "courtice"}

_PLACE_RE = re.compile(r"(?<![a-z])(" + "|".join(sorted((re.escape(k) for k in ONTARIO_PLACES), key=len, reverse=True)) + r")(?![a-z])")


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _has_code(text: str, codes) -> bool:
    return any(re.search(r"(?<![A-Za-z])" + c + r"(?![A-Za-z])", text) for c in codes)


def classify(location_text: str, home=(44.0592, -79.4613)) -> dict:
    """Return {region: 'ontario'|'canada-unknown'|'other-canada'|'foreign'|'unknown', city, km, remote}."""
    raw = (location_text or "").strip()
    low = raw.lower()
    out = {"region": "unknown", "city": None, "km": None, "remote": bool(re.search(r"\bremote\b", low))}
    if not raw:
        return out
    ontario_signal = bool(re.search(r"\bontario\b", low) or _has_code(raw, ["ON"]) or re.search(r"\bon,\s*ca", low))
    canada_signal = "canada" in low or bool(re.search(r"\bcan\b", low)) or bool(re.search(r"\bca\b", low) and ontario_signal)
    m = _PLACE_RE.search(low)
    city = m.group(1) if m else None

    other_prov = any(w in low for w in OTHER_PROVINCES) or _has_code(raw, PROVINCE_CODES)
    foreign = any(re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", low) for w in FOREIGN_WORDS) or (
        _has_code(raw, US_STATE_CODES) and not ontario_signal and not canada_signal)

    if city and (city not in AMBIGUOUS or ontario_signal or (canada_signal and not other_prov)):
        lat, lon = ONTARIO_PLACES[city]
        out.update(region="ontario", city=city.title(), km=round(haversine_km(home[0], home[1], lat, lon)))
        return out
    if ontario_signal:
        out["region"] = "ontario"
        return out
    if other_prov:
        out["region"] = "other-canada"
        return out
    if foreign:
        out["region"] = "foreign"
        return out
    if canada_signal:
        out["region"] = "canada-unknown"
    return out


def combine(locations: list[str], home=(44.0592, -79.4613)) -> dict:
    """For multi-location postings: keep the closest Ontario location."""
    best = None
    seen_regions = []
    for loc in locations:
        c = classify(loc, home)
        seen_regions.append(c["region"])
        if c["region"] == "ontario":
            if best is None or (c["km"] is not None and (best["km"] is None or c["km"] < best["km"])):
                best = c
    if best:
        return best
    for r in ("canada-unknown", "unknown", "other-canada", "foreign"):
        if r in seen_regions:
            return {"region": r, "city": None, "km": None, "remote": False}
    return {"region": "unknown", "city": None, "km": None, "remote": False}

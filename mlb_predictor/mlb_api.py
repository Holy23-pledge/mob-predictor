"""MLB Stats API client (statsapi.mlb.com). All calls cached via fetch."""
from __future__ import annotations

from .fetch import get_json

BASE = "https://statsapi.mlb.com/api/v1"

FIELDS_TEAMS = "fields=teams,id,name,abbreviation,teamName,clubName,shortName"
FIELDS_STANDINGS = ("fields=records,teamRecords,team,id,name,wins,losses,"
                    "runsScored,runsAllowed,splitRecords,type,pct")


def teams(season: int) -> list[dict]:
    return get_json(f"{BASE}/teams?sportId=1&season={season}&{FIELDS_TEAMS}")["teams"]


def find_team(name_or_abbrev: str, season: int) -> dict:
    q = name_or_abbrev.strip().lower()
    for t in teams(season):
        candidates = {t["name"].lower(), t.get("teamName", "").lower(),
                      t.get("abbreviation", "").lower(), t.get("clubName", "").lower(),
                      t.get("shortName", "").lower()}
        if q in candidates or any(q in c for c in candidates if c):
            return t
    raise ValueError(f"Team not found: {name_or_abbrev!r}")


def schedule(date: str) -> list[dict]:
    url = (f"{BASE}/schedule?sportId=1&date={date}"
           f"&hydrate=probablePitcher,venue")
    # ttl=0: the day's schedule is ALWAYS fetched fresh.
    data = get_json(url, ttl=0)
    if not data.get("dates"):
        return []
    return data["dates"][0]["games"]


def standings(season: int) -> dict[int, dict]:
    url = (f"{BASE}/standings?leagueId=103,104&season={season}"
           f"&standingsTypes=regularSeason&{FIELDS_STANDINGS}")
    out = {}
    for rec in get_json(url)["records"]:
        for tr in rec["teamRecords"]:
            out[tr["team"]["id"]] = tr
    return out


def split_record(team_record: dict, split_type: str) -> tuple[int, int]:
    for sr in team_record.get("records", {}).get("splitRecords", []):
        if sr.get("type") == split_type:
            return sr.get("wins", 0), sr.get("losses", 0)
    return 0, 0


def team_stats(team_id: int, season: int, group: str) -> dict:
    url = f"{BASE}/teams/{team_id}/stats?stats=season&group={group}&season={season}"
    data = get_json(url)
    try:
        return data["stats"][0]["splits"][0]["stat"]
    except (KeyError, IndexError):
        return {}


def roster(team_id: int, season: int, roster_type: str = "active") -> list[dict]:
    url = (f"{BASE}/teams/{team_id}/roster?rosterType={roster_type}"
           f"&season={season}&fields=roster,person,id,fullName,position,"
           f"abbreviation,status,code,description")
    return get_json(url).get("roster", [])


def il_players(team_id: int, season: int) -> list[dict]:
    out = []
    for r in roster(team_id, season, "40Man"):
        status = r.get("status", {})
        code, desc = status.get("code", ""), status.get("description", "")
        if code.startswith("D") or "Injured" in desc:
            out.append({"id": r["person"]["id"], "name": r["person"]["fullName"],
                        "position": r.get("position", {}).get("abbreviation", "?"),
                        "status": desc or code})
    return out


def people_stats(person_ids: list[int], season: int,
                 groups: str = "hitting") -> list[dict]:
    if not person_ids:
        return []
    ids = ",".join(str(i) for i in sorted(person_ids))
    url = (f"{BASE}/people?personIds={ids}"
           f"&hydrate=stats(group=[{groups}],type=[season],season={season})")
    return get_json(url).get("people", [])


def bvp(batter_ids: list[int], pitcher_id: int) -> dict[int, dict]:
    if not batter_ids:
        return {}
    ids = ",".join(str(i) for i in sorted(batter_ids))
    url = (f"{BASE}/people?personIds={ids}"
           f"&hydrate=stats(group=[hitting],type=[vsPlayerTotal],"
           f"opposingPlayerId={pitcher_id})")
    out = {}
    for person in get_json(url).get("people", []):
        for block in person.get("stats", []):
            if block.get("type", {}).get("displayName") == "vsPlayerTotal":
                for split in block.get("splits", []):
                    out[person["id"]] = split.get("stat", {})
    return out


def pitcher_season(pid: int, season: int) -> dict:
    url = (f"{BASE}/people/{pid}/stats?stats=season&group=pitching"
           f"&season={season}&fields=stats,splits,stat,era,whip,"
           f"inningsPitched,homeRuns,baseOnBalls,hitBatsmen,strikeOuts")
    data = get_json(url)
    try:
        return data["stats"][0]["splits"][0]["stat"]
    except (KeyError, IndexError):
        return {}


def pitch_arsenal(pid: int, season: int) -> list[dict]:
    url = f"{BASE}/people/{pid}/stats?stats=pitchArsenal&group=pitching&season={season}"
    data = get_json(url)
    out = []
    try:
        splits = data["stats"][0]["splits"]
    except (KeyError, IndexError):
        return out
    for s in splits:
        st = s["stat"]
        out.append({"code": st["type"]["code"],
                    "description": st["type"]["description"],
                    "pct": st.get("percentage", 0.0),
                    "velo": st.get("averageSpeed", 0.0)})
    return sorted(out, key=lambda x: -x["pct"])


def venue_info(venue_id: int) -> dict:
    url = f"{BASE}/venues/{venue_id}?hydrate=location,fieldInfo,timezone"
    venues = get_json(url).get("venues", [])
    return venues[0] if venues else {}


def parse_ip(ip_str) -> float:
    """'104.1' -> 104.333 (baseball innings notation)."""
    try:
        s = str(ip_str)
        if "." in s:
            whole, frac = s.split(".")
            return int(whole) + int(frac) / 3.0
        return float(s)
    except (ValueError, TypeError):
        return 0.0

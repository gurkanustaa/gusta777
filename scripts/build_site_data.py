from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from etl.sportmonks_api import SportmonksClient, date_chunks

OUT = Path("docs/data/site.json")


def participant(f, location):
    return next((p for p in f.get("participants", []) if p.get("meta", {}).get("location") == location), None)


def score(f, description, location):
    for row in f.get("scores", []):
        s = row.get("score", {})
        if row.get("description") == description and s.get("participant") == location:
            return s.get("goals")
    return None


def load(client, start, end):
    rows = []
    for a, b in date_chunks(start, end, 100):
        rows += client.get_fixtures(a, b)
    return sorted({x["id"]: x for x in rows}.values(), key=lambda x: x.get("starting_at", ""))


def snapshot(rows):
    rows = rows[-10:]
    n = len(rows)
    if not n:
        return {"n": 0, "gf": 0, "ga": 0, "ppg": 1.2, "fh": .25, "sh": .35, "full": .5, "form": "-"}
    points = sum(3 if r["gf"] > r["ga"] else 1 if r["gf"] == r["ga"] else 0 for r in rows)
    form = " ".join("G" if r["gf"] > r["ga"] else "B" if r["gf"] == r["ga"] else "M" for r in rows[-5:])
    return {"n": n, "gf": sum(r["gf"] for r in rows)/n, "ga": sum(r["ga"] for r in rows)/n, "ppg": points/n,
            "fh": sum(r["fh"] for r in rows)/n, "sh": sum(r["sh"] for r in rows)/n,
            "full": sum(r["full"] for r in rows)/n, "form": form}


def probs(home, away, league_fh, league_sh):
    strength = max(-2, min(2, (home["ppg"]-away["ppg"]) + .2*((home["gf"]-home["ga"])-(away["gf"]-away["ga"]))))
    raw = [max(.12, .44+.085*strength), max(.16, .27-.025*abs(strength)), max(.10, .29-.075*strength)]
    total = sum(raw)
    p = [x/total for x in raw]
    fh = max(.05, min(.90, .45*home["fh"]+.45*away["fh"]+.10*league_fh))
    sh = max(.05, min(.92, .45*home["sh"]+.45*away["sh"]+.10*league_sh))
    confidence = max(.50, min(.86, .50+.024*min(home["n"], away["n"], 10)+.12*max(abs(fh-.5), abs(sh-.5))))
    return p, fh, sh, confidence


def main():
    if not os.getenv("SPORTMONKS_API_TOKEN"):
        print("No API token; existing demo data kept.")
        return
    today = date.today()
    fixtures = load(SportmonksClient(), today-timedelta(days=365), today+timedelta(days=14))
    history, names, completed = defaultdict(list), {}, []
    for f in fixtures:
        h, a = participant(f, "home"), participant(f, "away")
        if not h or not a:
            continue
        names[h["id"]], names[a["id"]] = h.get("name"), a.get("name")
        hf, af = score(f,"CURRENT","home"), score(f,"CURRENT","away")
        hh, ah = score(f,"1ST_HALF","home"), score(f,"1ST_HALF","away")
        if hf is None or af is None or hh is None or ah is None or f.get("starting_at","")[:10] >= today.isoformat():
            continue
        fh = int(hh>0 and ah>0); sh = int((hf-hh)>0 and (af-ah)>0); full = int(hf>0 and af>0)
        history[h["id"]].append({"gf":hf,"ga":af,"fh":fh,"sh":sh,"full":full})
        history[a["id"]].append({"gf":af,"ga":hf,"fh":fh,"sh":sh,"full":full})
        completed.append({"gf":hf,"ga":af,"fh":fh,"sh":sh})
    snaps = {k:snapshot(v) for k,v in history.items()}
    n = len(completed); lfh = sum(x["fh"] for x in completed)/n if n else .25; lsh = sum(x["sh"] for x in completed)/n if n else .35
    upcoming = []
    for f in fixtures:
        if f.get("starting_at","")[:10] < today.isoformat(): continue
        h, a = participant(f,"home"), participant(f,"away")
        if not h or not a: continue
        hp, ap = snaps.get(h["id"],snapshot([])), snaps.get(a["id"],snapshot([]))
        p, fh, sh, conf = probs(hp,ap,lfh,lsh)
        upcoming.append({"match_id":f.get("id"),"home_team":h.get("name"),"away_team":a.get("name"),"kickoff_label":f.get("starting_at","").replace("T"," ")[:16],"home_win":p[0],"draw":p[1],"away_win":p[2],"first_half_btts":fh,"second_half_btts":sh,"confidence":conf,"model_label":"Trend v0"})
        if len(upcoming) == 10: break
    teams = [{"team":names.get(k,str(k)),"matches":v["n"],"goals_for_avg":v["gf"],"goals_against_avg":v["ga"],"first_half_btts_rate":v["fh"],"second_half_btts_rate":v["sh"],"full_match_btts_rate":v["full"],"form":v["form"]} for k,v in sorted(snaps.items(), key=lambda x:names.get(x[0],""))]
    payload = {"mode":"live","generated_at":datetime.now(timezone.utc).isoformat(),"model":"trend-v0","league":{"matches":n,"goals_per_match":sum(x["gf"]+x["ga"] for x in completed)/n if n else 0,"first_half_btts_rate":lfh,"second_half_btts_rate":lsh},"matches":upcoming,"teams":teams}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")

if __name__ == "__main__": main()

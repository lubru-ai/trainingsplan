#!/usr/bin/env python3
"""Garmin-Aktivitäten in den Sync-Gist der Trainingsplan-App schreiben.

Aufruf:  python3 tools/garmin_sync.py <aktivitaeten.json>

<aktivitaeten.json> ist eine Liste von Garmin-Aktivitäten, wie sie der
Garmin-Connector liefert (garmin_search_activities). Es reichen die Felder
activityId, activityName, startTimeLocal, activityType.typeKey,
activityType.parentTypeId, duration (s), distance (m), avgPower, averageHR.

Das Skript fasst sie pro Tag zusammen und schreibt sie unter "garmin" in den
privaten Gist "trainingsplan-sync (Trainingsplan App)". Die App hakt damit
Rad- und Laufeinheiten automatisch ab. Es ersetzt nur Tage, die in der Liste
vorkommen, und schreibt nur, wenn sich etwas geändert hat. Alles andere im
Gist (Einträge, Gewichte, Plananpassungen) bleibt unverändert.
"""
import json
import os
import subprocess
import sys
import time

GH = os.path.expanduser("~/.local/bin/gh")
DESC = "trainingsplan-sync (Trainingsplan App)"
FILE = "trainingsplan-data.json"

BIKE_PARENT, RUN_PARENT = 2, 17
BIKE_KEYS = ("cycling", "biking", "virtual_ride", "bmx")
RUN_KEYS = ("running",)


def gh(*args, stdin=None):
    r = subprocess.run([GH, *args], input=stdin, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"gh {' '.join(args[:3])} fehlgeschlagen: {r.stderr.strip()}")
    return r.stdout


def kind_of(t):
    key = (t.get("typeKey") or "").lower()
    parent = t.get("parentTypeId")
    if parent == BIKE_PARENT or any(k in key for k in BIKE_KEYS):
        return "bike"
    if parent == RUN_PARENT or any(k in key for k in RUN_KEYS):
        return "run"
    return "other"


def compact(a):
    t = a.get("activityType") or {}
    out = {
        "id": a.get("activityId"),
        "kind": kind_of(t),
        "type": t.get("typeKey") or "",
        "name": (a.get("activityName") or "").replace("​", "").strip(),
        "start": (a.get("startTimeLocal") or "")[11:16],
        "min": round((a.get("duration") or 0) / 60, 1),
    }
    if a.get("distance"):
        out["km"] = round(a["distance"] / 1000, 2)
    if a.get("avgPower"):
        out["w"] = round(a["avgPower"])
    if a.get("averageHR"):
        out["hr"] = round(a["averageHR"])
    return out


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    acts = json.load(open(sys.argv[1], encoding="utf-8"))
    if isinstance(acts, dict):
        acts = acts.get("activities") or acts.get("items") or []
    by_day = {}
    for a in acts:
        day = (a.get("startTimeLocal") or "")[:10]
        if len(day) == 10:
            by_day.setdefault(day, []).append(compact(a))
    for day in by_day:
        by_day[day].sort(key=lambda x: x["start"])

    gists = json.loads(gh("api", "gists?per_page=100"))
    gist = next((g for g in gists if g.get("description") == DESC and FILE in (g.get("files") or {})), None)
    if not gist:
        sys.exit("Sync-Gist nicht gefunden. Ist der Geräte-Sync in der App eingerichtet?")
    content = json.loads(gh("api", f"gists/{gist['id']}", "--jq", f'.files["{FILE}"].content') or "{}")

    garmin = content.setdefault("garmin", {})
    now = int(time.time() * 1000)
    changed = []
    for day, day_acts in sorted(by_day.items()):
        old = (garmin.get(day) or {}).get("acts")
        if old != day_acts:
            garmin[day] = {"acts": day_acts, "u": now}
            changed.append(day)

    if not changed:
        print(f"Keine Änderungen. {len(acts)} Aktivitäten an {len(by_day)} Tagen geprüft.")
        return
    body = json.dumps({"files": {FILE: {"content": json.dumps(content, ensure_ascii=False)}}}, ensure_ascii=False)
    gh("api", "-X", "PATCH", f"gists/{gist['id']}", "--input", "-", stdin=body)
    for day in changed:
        names = ", ".join(f"{a['type']} {a['min']:.0f} min" for a in garmin[day]["acts"])
        print(f"{day}: {names}")
    print(f"{len(changed)} Tag(e) aktualisiert.")


if __name__ == "__main__":
    main()

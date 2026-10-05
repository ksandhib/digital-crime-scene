"""Shared helpers for the analyst agents.

A `View` wraps a case bundle and exposes only what the player is allowed to know:
evidence that has been discovered (or everything, for generator self-checks).
"""
import re

REL_W = {"HIGH": 1.0, "MEDIUM": 0.7, "LOW": 0.35, "QUESTIONABLE": 0.15}
RELIABILITY = ["HIGH", "MEDIUM", "LOW", "QUESTIONABLE"]

ACTION_TYPES = {"device_unlock", "session_active", "file_access", "file_modify", "ext_connect",
                "ext_action", "device_lock"}
BADGE_TYPES = {"badge_in", "badge_out", "badge_room"}

EVENT_LABELS = {
    "badge_in": "Badge: entered building", "badge_out": "Badge: left building",
    "badge_room": "Badge: room entry", "device_unlock": "Device unlocked",
    "session_active": "Session resumed", "session_idle": "Session left idle",
    "file_access": "File accessed", "file_modify": "File modified",
    "ext_connect": "External device connected", "ext_action": "External transfer",
    "device_lock": "Device locked", "camera_detect": "Camera detection",
    "message_deleted": "Message deleted", "system_job": "System job",
    "server_access": "Server file read", "policy_purge": "Retention policy purge",
}


def fmt(minute):
    if minute is None:
        return "--:--"
    minute = int(minute)
    return f"{minute // 60:02d}:{minute % 60:02d}"


def parse_hhmm(text):
    m = re.search(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b", text or "")
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


class View:
    def __init__(self, bundle, all_discovered=False):
        self.b = bundle
        self.case = bundle["case"]
        self.alert_minute = self.case["alert_minute"]
        self.ev = {e["id"]: e for e in bundle["evidence"]}
        self.disc = {i for i, e in self.ev.items() if all_discovered or e.get("discovered")}
        self.suspects = bundle["suspects"]
        self.victim = bundle["victims"][0] if bundle["victims"] else None
        self.witnesses = bundle["witnesses"]
        self.persons = {p["ref"]: p for p in self.suspects + bundle["victims"] + self.witnesses}
        self.devices = {d["ref"]: d for d in bundle["devices"]}
        self.locs = {l["ref"]: l for l in bundle["locations"]}
        self.events = sorted([e for e in bundle["events"] if e["evidence_id"] in self.disc],
                             key=lambda e: (e["minute"], e["ref"]))
        self.emails = [e for e in bundle["emails"] if e["evidence_id"] in self.disc]
        self.messages = [m for m in bundle["messages"] if m["evidence_id"] in self.disc]
        self.images = [i for i in bundle["images"] if i["evidence_id"] in self.disc]
        self.files = {f["ref"]: f for f in bundle["files"]}
        tf = [f for f in bundle["files"] if (f.get("extra") or {}).get("target")]
        self.target_file = tf[0] if tf else None
        self.target_loc = self.case["location_ref"]

    # ---- names
    def name(self, ref):
        if ref in self.persons:
            return self.persons[ref]["name"]
        if ref in self.devices:
            return self.devices[ref]["name"]
        if ref in self.locs:
            return self.locs[ref]["name"]
        if ref in self.files:
            return self.files[ref]["filename"]
        return ref or "unknown"

    def first(self, ref):
        return self.name(ref).split()[0] if ref in self.persons else self.name(ref)

    # ---- evidence helpers
    def rel(self, eid):
        e = self.ev.get(eid)
        return REL_W.get(e["reliability"], 0.5) if e else 0.5

    def relf(self, eids):
        eids = [e for e in eids if e in self.ev]
        if not eids:
            return 1.0
        return sum(self.rel(e) for e in eids) / len(eids)

    def is_disc(self, eid):
        return eid in self.disc

    def evidence_of(self, ref):
        return [e for e in self.ev.values() if ref in (e.get("entities") or []) and e["id"] in self.disc]

    def events_of(self, etype=None, device=None, actor=None):
        out = []
        for e in self.events:
            if etype and e["type"] != etype:
                continue
            if device and e["device_ref"] != device:
                continue
            if actor and e["actor_ref"] != actor:
                continue
            out.append(e)
        return out


def evid_list(text):
    return re.findall(r"E-\d{3}", text or "")

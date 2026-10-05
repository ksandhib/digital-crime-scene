"""Procedural case generator (the 'Case Director' builds the truth first, then every
piece of evidence is derived from it).

Pipeline:  seed -> hidden truth (who / why / how / when) -> actors, devices, locations
           -> chain of key events -> red herrings -> noise -> ids -> relationships -> validation
"""
import hashlib
import random
import re
import secrets
from datetime import date

from ..agents.common import fmt
from ..agents import case_director
from .content import (FIRST, LAST, ROLES, COMPANIES, COMPETITORS, PROJECTS, LENDERS, LOCATIONS, INCIDENTS,
                      METHODS, MOTIVES, DIFF, NOISE_CHATS)

TOK = re.compile(r"~T\d{3}")
ISREF = re.compile(r"^[PVW]-\d\d$")


def new_seed():
    return "%04X-%04X" % (secrets.randbelow(65536), secrets.randbelow(65536))


def normalize_seed(s):
    s = (s or "").strip().upper()
    if re.fullmatch(r"[0-9A-F]{4}-[0-9A-F]{4}", s):
        return s
    if not s:
        return new_seed()
    h = hashlib.sha1(s.encode()).hexdigest().upper()
    return h[:4] + "-" + h[4:8]


def case_id_for(seed, difficulty):
    return f"{seed}-{ {'EASY': 'E', 'MEDIUM': 'M', 'HARD': 'H', 'EXPERT': 'X'}[difficulty] }"


def round5(m):
    return int(5 * round(m / 5.0))


def remap(obj, idmap):
    if isinstance(obj, str):
        return TOK.sub(lambda m: idmap.get(m.group(0), m.group(0)), obj)
    if isinstance(obj, list):
        return [remap(x, idmap) for x in obj]
    if isinstance(obj, dict):
        return {k: remap(v, idmap) for k, v in obj.items()}
    return obj


class Gen:
    def __init__(self, seed, difficulty, ctype, attempt):
        self.seed, self.diff, self.ctype, self.attempt = seed, difficulty, ctype, attempt
        self.P = DIFF[difficulty]
        self.r = random.Random(f"{seed}|{difficulty}|{ctype}|{attempt}")
        self.evs, self.events, self.emails, self.messages = [], [], [], []
        self.files, self.images = [], []
        self.roles, self.nt = {}, 0

    # ---------------------------------------------------------------- primitives
    def tok(self):
        self.nt += 1
        return f"~T{self.nt:03d}"

    def dp(self, base, hard=0):
        d = base + self.P["dshift"] + (hard if self.diff in ("HARD", "EXPERT") else 0)
        return max(1, min(3, d))

    def nm(self, ref):
        return self.names.get(ref, ref or "unknown")

    def ev(self, typ, title, minute, rel, ents, summary, depth=1, data=None, role="noise", init=False, first=False):
        k = self.tok()
        ents = [e for e in dict.fromkeys(ents) if e and (ISREF.match(e) or e[:2] in ("D-", "L-", "F-"))]
        self.evs.append(dict(key=k, type=typ, title=title, minute=int(minute), reliability=rel, entities=ents,
                             summary=summary, depth=depth, data=data or {}, init=init, first=first,
                             order=len(self.evs), source_ref=None))
        self.roles[k] = role
        return k

    def evt(self, minute, etype, actor, device, loc, desc, evk, data=None):
        self.events.append(dict(ref=None, evidence_id=evk, minute=int(minute), type=etype, actor_ref=actor,
                                device_ref=device, location_ref=loc, description=desc, data=data or {}))

    def log(self, typ, minute, rel, etype, actor, device, loc, desc, depth=1, role="noise", data=None, title=None,
            extra_ents=(), node=False, init=False):
        d = dict(data or {})
        if node:
            d["node"] = True
        k = self.ev(typ, title or desc, minute, rel, [actor, device, loc, *extra_ents],
                    f"{fmt(minute)} - {desc}", depth, {}, role, init)
        self.evt(minute, etype, actor, device, loc, desc, k, d)
        return k

    def email(self, sender, rcpts, subject, minute, body, rel, depth, role="noise", cc=(), attachments=(),
              origin=None, data=None, ents=(), init=False, first=False, org=None):
        refs = [x for x in [sender, *rcpts, *ents] if x and ISREF.match(x)]
        to_names = ", ".join(self.nm(x) if ISREF.match(x) else x for x in rcpts)
        k = self.ev("EMAIL", f"Email: {subject}", minute, rel, refs,
                    f"{self.nm(sender) if ISREF.match(sender) else sender} -> {to_names}: {subject}",
                    depth, data, role, init, first)
        self.emails.append(dict(ref=None, evidence_id=k, sender=sender, recipients=list(rcpts), cc=list(cc),
                                subject=subject, minute=int(minute), body=body, attachments=list(attachments),
                                extra={"origin_device": origin, "org": org}))
        return k

    def msg(self, a, b, lines, rel, depth, label, role="noise", data=None, ents=(), init=False):
        """lines: [(speaker, minute, text)] - speaker is a ref or a display name."""
        refs = [x for x in [a, b, *ents] if x and ISREF.match(x)]
        rows = [{"from": s if ISREF.match(s) else None, "name": self.nm(s) if ISREF.match(s) else s,
                 "minute": int(m), "text": t} for s, m, t in lines]
        na = self.nm(a) if ISREF.match(a) else a
        nb = self.nm(b) if ISREF.match(b) else b
        k = self.ev("MESSAGE", f"Messages: {na} / {nb}", rows[0]["minute"], rel, refs,
                    f"{label} ({len(rows)} messages)", depth, data, role, init)
        self.messages.append(dict(ref=None, evidence_id=k, a=a, b=b, minute=rows[0]["minute"], lines=rows,
                                  extra={"label": label, "a_name": na, "b_name": nb}))
        return k

    def image(self, minute, loc, dev, caption, meta, rel, depth, scene, role="noise", actor=None, ents=(),
              etype=None, desc=None):
        k = self.ev("IMAGE", caption, minute, rel, [actor, dev, loc, *ents], f"{fmt(minute)} - {caption}", depth, {},
                    role)
        self.images.append(dict(ref=None, evidence_id=k, minute=int(minute), location_ref=loc, device_ref=dev,
                                caption=caption, metadata=meta, extra={"scene": scene, "actor": actor}))
        if etype:
            self.evt(minute, etype, actor, dev, loc, desc or caption, k)
        return k

    # ---------------------------------------------------------------- build
    def build(self):
        r, P = self.r, self.P
        inc_key = self.ctype if self.ctype in INCIDENTS else r.choice(sorted(INCIDENTS))
        inc = INCIDENTS[inc_key]
        comp, dom = r.choice(COMPANIES)
        competitor = r.choice(COMPETITORS)
        project = r.choice(PROJECTS)
        day = date(2047, r.randint(1, 12), r.randint(1, 28))
        self.day = day.isoformat()
        n = P["n"]
        method = r.choice(P["methods"])
        motive = r.choice(sorted(MOTIVES))

        # ---- people
        firsts, lasts = r.sample(FIRST, n + 3), r.sample(LAST, n + 3)
        roles = r.sample(ROLES, n)
        S = []
        for i in range(n):
            S.append(dict(ref=f"P-{i+1:02d}", name=f"{firsts[i]} {lasts[i]}", first=firsts[i], role=roles[i],
                          age=r.randint(24, 55), access_level=r.choice(["LOW", "MEDIUM", "MEDIUM", "HIGH"]),
                          email=f"{firsts[i].lower()}@{dom}.local", bio="", alibi="", extra={}))
        V = dict(ref="V-01", name=f"Dr. {firsts[n]} {lasts[n]}", first=firsts[n], role="Director of Research",
                 age=r.randint(41, 62), access_level="HIGH", email=f"{firsts[n].lower()}@{dom}.local", bio="",
                 alibi="", extra={})
        W1 = dict(ref="W-01", name=f"{firsts[n+1]} {lasts[n+1]}", first=firsts[n + 1],
                  role="Security Officer (lobby desk)", age=r.randint(30, 60), access_level="MEDIUM",
                  email=f"{firsts[n+1].lower()}@{dom}.local", bio="", alibi="", extra={})
        W2 = dict(ref="W-02", name=f"{firsts[n+2]} {lasts[n+2]}", first=firsts[n + 2],
                  role="Facilities Technician (night shift)", age=r.randint(25, 60), access_level="LOW",
                  email=f"{firsts[n+2].lower()}@{dom}.local", bio="", alibi="", extra={})
        self.names = {p["ref"]: p["name"] for p in S + [V, W1, W2]}
        pi = r.randrange(n)
        perp = S[pi]
        others = [s for s in S if s is not perp]
        r.shuffle(others)
        owner = others.pop() if method == "colleague_unlocked" else None
        slot = {}
        for d in P["decoys"]:
            if others:
                slot[d] = others.pop(0)
            else:
                pool = [s for s in S if s is not perp and s is not owner]
                slot[d] = r.choice(pool) if pool else None
        loud, deleted, minor, bystander = (slot.get(k) for k in ("loud", "deleted", "minor", "bystander"))
        rolemap = {s["ref"]: "plain" for s in S}
        rolemap[perp["ref"]] = "perp"
        for key, s in (("owner", owner), ("loud", loud), ("deleted", deleted), ("minor", minor),
                       ("bystander", bystander)):
            if s is not None and rolemap[s["ref"]] == "plain":
                rolemap[s["ref"]] = key
        plain = [s for s in S if rolemap[s["ref"]] == "plain"]
        perp["access_level"] = "HIGH" if method == "own_workstation" else r.choice(["LOW", "MEDIUM"])
        if owner:
            owner["access_level"] = "HIGH"

        # ---- places & devices
        Lt = "L-02" if method == "shared_terminal" else "L-03"
        locs = [dict(ref=ref, name=name, building=(comp + " HQ") if b == "HQ" else "Parking Structure", extra={})
                for ref, name, b in LOCATIONS]
        home = {}
        for s in S:
            home[s["ref"]] = r.choice(["L-02", "L-03"])
        if method == "own_workstation":
            home[perp["ref"]] = Lt
        if owner:
            home[owner["ref"]] = Lt
        nums = r.sample(range(1, 30), n)
        D, dev_of = [], {}
        for i, s in enumerate(S):
            ref = f"D-{i+1:02d}"
            D.append(dict(ref=ref, name=f"Laptop #{nums[i]:02d}", kind="laptop", owner_ref=s["ref"],
                          location_ref=home[s["ref"]], extra={}))
            dev_of[s["ref"]] = ref
        serial = f"{inc['ext_prefix']}-{r.randint(100, 999)}"
        dec_serial = f"{inc['ext_prefix']}-{r.randint(100, 999)}"
        while dec_serial == serial:
            dec_serial = f"{inc['ext_prefix']}-{r.randint(100, 999)}"
        extra_devs = [("srv", "NEX-SRV-01", "server", None, "L-04", {}),
                      ("ext", f"{inc['ext_name']} {serial}", "external", None, None, {"serial": serial}),
                      ("badge", "Badge Controller BC-1", "badge_system", None, "L-01", {}),
                      ("gcam", "Garage Camera GC-2", "camera", None, "L-05", {}),
                      ("ccam", "Corridor Camera CC-7", "camera", None, Lt, {})]
        if method == "shared_terminal":
            extra_devs.append(("lab", "Lab Terminal LT-02", "terminal", None, "L-02", {}))
        dv = {}
        for key, name, kind, owner_ref, loc, ex in extra_devs:
            ref = f"D-{len(D)+1:02d}"
            D.append(dict(ref=ref, name=name, kind=kind, owner_ref=owner_ref, location_ref=loc, extra=ex))
            dv[key] = ref
        for d in D:
            self.names[d["ref"]] = d["name"]
        srv, ext, badge, gcam, ccam = dv["srv"], dv["ext"], dv["badge"], dv["gcam"], dv["ccam"]
        if method == "own_workstation":
            dev, acct = dev_of[perp["ref"]], perp["ref"]
        elif method == "colleague_unlocked":
            dev, acct = dev_of[owner["ref"]], owner["ref"]
        else:
            dev, acct = dv["lab"], None
        dname = self.nm(dev)
        for l in locs:
            self.names[l["ref"]] = l["name"]

        # ---- time frame
        tm = r.randint(22 * 60 + 55, 23 * 60 + 28)
        alert = tm + r.randint(18, 26)
        ms = r.randint(19 * 60 + 35, 20 * 60 + 25)
        perp_exit = tm + r.randint(12, 18)
        L_p = round5(tm - r.randint(30, 52))
        ext_name = inc["ext_name"]
        file_ref = "F-01"
        fname = inc["file"]

        # ---- exits & alibis
        exit_m = {perp["ref"]: perp_exit}
        for s in S:
            ro = rolemap[s["ref"]]
            if ro == "perp":
                continue
            if ro == "owner":
                exit_m[s["ref"]] = tm - r.randint(62, 85)
            elif ro == "loud":
                exit_m[s["ref"]] = tm - r.randint(38, 55)
            elif ro == "deleted":
                exit_m[s["ref"]] = tm - r.randint(32, 50)
            elif ro == "minor":
                exit_m[s["ref"]] = r.randint(20 * 60 + 56, 21 * 60 + 25)
            elif ro == "bystander":
                exit_m[s["ref"]] = tm + r.randint(20, 28)
            else:
                exit_m[s["ref"]] = r.randint(ms + 65, tm - 40)
        for s in S:
            ro = rolemap[s["ref"]]
            ex = exit_m[s["ref"]]
            s["extra"]["team"] = project
            s["extra"]["home_loc"] = home[s["ref"]]
            s["extra"]["role_kind"] = None  # never leaked
            if ro == "perp":
                s["extra"]["alibi_claim"] = {"type": "left", "minute": L_p, "text": f"I left the building at {fmt(L_p)}."}
                s["alibi"] = f"\"I left the building at {fmt(L_p)}.\""
            elif ro == "minor":
                L = round5(ex - r.randint(35, 50))
                s["extra"]["alibi_claim"] = {"type": "left", "minute": L,
                                             "text": f"I left around {fmt(L)} and went home."}
                s["alibi"] = f"\"I left around {fmt(L)} and went home.\""
            elif ro == "bystander":
                s["extra"]["alibi_claim"] = {"type": "stayed", "minute": ex, "location_ref": "L-04",
                                             "text": f"I stayed late for scheduled server maintenance, leaving shortly after {fmt(round5(ex))}."}
                s["alibi"] = f"\"I stayed late for scheduled server maintenance and left after {fmt(round5(ex))}.\""
            else:
                L = round5(ex + r.randint(-3, 3))
                s["extra"]["alibi_claim"] = {"type": "left", "minute": L, "text": f"I left at {fmt(L)}."}
                s["alibi"] = f"\"I left at {fmt(L)}.\"" if r.random() < 0.6 else f"\"I was gone by {fmt(L)}.\""
            s["bio"] = f"{s['role']}, {r.randint(1, 11)} years at {comp}. Assigned to {project}."
        V["bio"] = f"Leads {project}. Owner of the {inc['noun']}."
        W1["bio"] = "Lobby desk security officer on the evening shift."
        W2["bio"] = "Night-shift facilities technician. Routine rounds of the research floor."
        if self.P["deceptive"] and loud:
            W2["bio"] += f" An HR complaint involving {loud['name']} was closed last spring."

        acl = {V["ref"]}
        if method == "own_workstation":
            acl.add(perp["ref"])
        if owner:
            acl.add(owner["ref"])
        pool = [s for s in S if s is not perp and s["ref"] not in acl]
        r.shuffle(pool)
        for s in pool[:r.randint(1, 2)]:
            acl.add(s["ref"])
        acl = sorted(acl)

        # ---- context evidence: alert, file, meeting, arrivals
        alert_k = self.email(f"security-system@{dom}.local", [V["ref"]],
                             f"[ALERT] Integrity monitor: unexpected change to {fname}", alert,
                             f"File integrity monitor flagged an unexpected change to {fname}.\n"
                             f"Detected: {fmt(alert)}. Time of the change itself: not yet determined.\n"
                             f"Affected asset owner: {V['name']}. Please review badge, device and access logs.",
                             "HIGH", 1, role="context", ents=[file_ref, Lt], init=True, first=True)
        inv_day = day.isoformat()
        invite_k = self.email(V["ref"], [s["ref"] for s in S], f"{project}: status review at {fmt(ms)} (Conference Room C)",
                              9 * 60 + 5, f"Team - status review today at {fmt(ms)} in Conference Room C. "
                              f"Please bring your latest results on the {inc['noun']}. Badge in at the conference room reader.",
                              "HIGH", 1, role="context", ents=["L-06"])
        mt = []
        for s in S + [V]:
            m = ms + r.randint(-3, 4)
            mt.append((s["ref"], m))
        k_meet = self.ev("ACCESS_LOG", "Badge log: Conference Room C entries", min(m for _, m in mt), "HIGH",
                         [x for x, _ in mt] + ["L-06", badge], f"{len(mt)} badge entries around {fmt(ms)}",
                         self.dp(2), {}, "context")
        for ref, m in mt:
            self.evt(m, "badge_room", ref, badge, "L-06", f"Badge entry: {self.nm(ref)} -> Conference Room C", k_meet)
        arr = [(s["ref"], r.randint(8 * 60 + 10, 9 * 60 + 45)) for s in S + [V]]
        k_arr = self.ev("ACCESS_LOG", "Badge log: morning arrivals", min(m for _, m in arr), "HIGH",
                        [x for x, _ in arr] + ["L-01", badge], f"{len(arr)} badge entries, building entrance", self.dp(2),
                        {}, "context", init=(self.diff == "EASY"))
        for ref, m in arr:
            self.evt(m, "badge_in", ref, badge, "L-01", f"Badge entry: {self.nm(ref)} -> Main Lobby", k_arr)

        # ---- KEY CHAIN
        key = []
        t_room = tm - 9
        key.append(self.log("ACCESS_LOG", t_room, "HIGH", "badge_room", perp["ref"], badge, Lt,
                            f"Badge entry: {perp['name']} -> {self.nm(Lt)}", self.dp(2), "key"))
        if method == "own_workstation":
            ud = f"{dname} unlocked by {perp['first']}"
            u_type = "device_unlock"
        elif method == "colleague_unlocked":
            ud = f"{dname}: input resumed after 62 min idle (session: {owner['first']})"
            u_type = "session_active"
        else:
            ud = f"{dname} unlocked (account: shared-lab)"
            u_type = "device_unlock"
        k_unlock = self.log("DEVICE_LOG", tm - 7, "HIGH", u_type, acct, dev, Lt, ud, self.dp(1), "key")
        k_access = self.log("DEVICE_LOG", tm - 2, "HIGH", "file_access", acct, dev, Lt,
                            f"{fname} accessed on {dname}", self.dp(2), "key")
        k_modify = self.log("DEVICE_LOG", tm, "HIGH", "file_modify", acct, dev, Lt,
                            f"{inc['modify']}: {fname}", self.dp(1), "key", node=True)
        k_extc = self.log("DEVICE_LOG", tm + 2, "HIGH", "ext_connect", acct, dev, Lt,
                          f"{inc['connect']} ({serial})", self.dp(2), "key", data={"serial": serial},
                          extra_ents=[ext])
        k_exta = self.log("DEVICE_LOG", tm + 3, "HIGH", "ext_action", acct, dev, Lt,
                          f"{inc['action']} ({serial})", self.dp(2, 1), "key", data={"serial": serial},
                          extra_ents=[ext], node=True)
        key += [k_unlock, k_access, k_modify, k_extc, k_exta]
        if method != "colleague_unlocked":
            key.append(self.log("DEVICE_LOG", tm + 5, "HIGH", "device_lock", acct, dev, Lt,
                                f"{dname} locked", self.dp(2), "key"))
        k_pexit = self.log("ACCESS_LOG", perp_exit, "HIGH", "badge_out", perp["ref"], badge, "L-01",
                           f"Badge exit: {perp['name']}", self.dp(2), "key")
        key.append(k_pexit)
        k_pcam = self.image(perp_exit + r.randint(8, 12), "L-05", gcam,
                            f"Garage exit lane: vehicle registered to {perp['name']}",
                            {"camera": "GC-2", "plate": f"NX-{r.randint(1000, 9999)}", "direction": "exit",
                             "clock": "server-synced"}, "MEDIUM", self.dp(2), "parking", "support",
                            actor=perp["ref"], etype="camera_detect")
        # prep email (after stated departure)
        rcpt = r.choice([s for s in S if s is not perp])
        k_prep = self.email(perp["ref"], [rcpt["ref"]], "Project Archive", tm - 11,
                            f"Hi {rcpt['first']}, quick one - is the final {project} archive still under the "
                            f"/research/{project.split()[-1].lower()}/final share? Want to double-check the folder "
                            f"before tomorrow. Thanks.", "HIGH", self.dp(2), role="key",
                            origin=(dev_of[perp["ref"]] if method == "own_workstation" else "Mobile mail client"))
        key.append(k_prep)
        # asset registry (links the external device to the perpetrator)
        k_asset = self.ev("SYSTEM", f"Asset registry: {serial} checked out", 17 * 60 + r.randint(0, 40), "HIGH",
                          [perp["ref"], ext, srv], f"{serial} checked out to {perp['name']}; not returned",
                          self.dp(3), {"asset": {"serial": serial, "person": perp["ref"], "action": "checkout"},
                                       "text": f"Equipment checkout record: {inc['ext_name']} {serial} issued to "
                                               f"{perp['name']}. Status: NOT RETURNED."}, "key")
        key.append(k_asset)
        # corridor image
        k_corr = self.image(tm - 8, Lt, ccam, f"Corridor outside {self.nm(Lt)}: figure in dark jacket at door",
                            {"camera": "CC-7", "light": "low", "face_visible": False,
                             "timestamp_source": "embedded in file, not server-verified"},
                            "QUESTIONABLE", self.dp(2), "corridor", "support", ents=[Lt])
        # motive evidence
        mk = self.motive_evidence(perp, motive, V, S, competitor, comp, project, tm, dom)
        key += mk

        # ---- witnesses
        last_out = perp["ref"]
        if self.P["guard_clear"]:
            k_guard = self.ev("WITNESS", f"Statement: {W1['name']} (security officer)", alert + 40, "MEDIUM",
                              [W1["ref"], "L-01", perp["ref"]], "Reports who was last through the lobby",
                              self.dp(2), {"text": f"I was on the lobby desk all evening. The last person I saw go out through the lobby "
                                                   f"was {perp['name']}, at about {fmt(perp_exit)}. Everyone else had gone before that.",
                                           "claims": [{"person": perp["ref"], "location_ref": "L-01", "minute": perp_exit,
                                                       "quote": f"last person out: {perp['name']}"}]}, "support")
            if bystander:
                self.evs[-1]["data"]["text"] = (f"I was on the lobby desk all evening. {perp['name']} was one of the last through "
                                                f"the lobby, around {fmt(perp_exit)}. The server room staff left a little after.")
        else:
            k_guard = self.ev("WITNESS", f"Statement: {W1['name']} (security officer)", alert + 40, "MEDIUM",
                              [W1["ref"], "L-01"], "Was away from the desk during the incident window", self.dp(2),
                              {"text": f"I did my rounds between {fmt(tm - 12)} and {fmt(tm + 25)}, so the lobby desk was unattended. "
                                       f"I can't tell you who came or went in that time.", "claims": []}, "noise")
        wclaims, wtext, wrole = [], "", "support"
        if self.P["deceptive"] and loud:
            wclaims = [{"person": loud["ref"], "location_ref": Lt, "minute": tm - 5,
                        "quote": f"saw {loud['name']} in {self.nm(Lt)}"}]
            wtext = (f"Around {fmt(tm - 5)} I passed {self.nm(Lt)} and saw {loud['name']} at a desk in there. "
                     f"I'm certain it was them.")
            wrole = "decoy"
        elif self.diff == "EASY":
            wclaims = [{"person": perp["ref"], "location_ref": Lt, "minute": tm - 8, "quote": f"looked like {perp['first']}"}]
            wtext = (f"Around {fmt(tm - 8)} I saw someone in a dark jacket going into {self.nm(Lt)}. "
                     f"From the walk, it looked like {perp['first']}.")
        else:
            wtext = (f"Around {fmt(tm - 8)} I noticed the door of {self.nm(Lt)} open and someone in a dark jacket at "
                     f"the desk. I didn't see a face.")
        k_clean = self.ev("WITNESS", f"Statement: {W2['name']} (facilities)", alert + 55, "MEDIUM",
                          [W2["ref"], Lt] + ([loud["ref"]] if wrole == "decoy" else []), "Describes someone near the incident room",
                          self.dp(2), {"text": wtext, "claims": wclaims}, wrole)

        # ---- exits, camera, locks for everyone else
        decoys = []
        exculp = []
        for s in S:
            if s is perp:
                continue
            ro, ex = rolemap[s["ref"]], exit_m[s["ref"]]
            d_exit = self.dp(2) if ro in ("owner", "loud", "deleted", "bystander") else self.dp(1 if self.diff != "HARD" else 2)
            k_exit = self.log("ACCESS_LOG", ex, "HIGH", "badge_out", s["ref"], badge, "L-01",
                              f"Badge exit: {s['name']}", d_exit, "exculpatory" if ro in ("owner", "loud", "deleted") else "noise")
            if ro in ("owner", "loud", "deleted"):
                exculp.append(k_exit)
            if ro in ("owner", "loud") or r.random() < 0.4:
                kc = self.image(ex + r.randint(7, 12), "L-05", gcam,
                                f"Garage exit lane: vehicle registered to {s['name']}",
                                {"camera": "GC-2", "plate": f"NX-{r.randint(1000, 9999)}", "direction": "exit",
                                 "clock": "server-synced"}, "MEDIUM", self.dp(2), "parking",
                                "exculpatory" if ro in ("owner", "loud") else "noise", actor=s["ref"], etype="camera_detect")
                if ro in ("owner", "loud"):
                    exculp.append(kc)
            if ro == "owner":
                k_idle = self.log("DEVICE_LOG", ex - 4, "HIGH", "session_idle", s["ref"], dev, Lt,
                                  f"{dname}: session ({s['first']}) left active; no lock event; last input {fmt(ex - 4)}",
                                  self.dp(2), "support")
                k_om = self.msg(s["ref"], "Sam (partner)", [
                    ("Sam (partner)", ex + 10, "Home yet?"),
                    (s["ref"], ex + 12, f"Just realised I left my laptop open in {self.nm(Lt)}. Too late to go back - "
                                        f"I'll lock it first thing tomorrow."),
                ], "MEDIUM", self.dp(2), "Laptop left open", role="support", ents=[Lt, dev])
                decoys.append(dict(kind="owner", suspect=s["ref"], evidence=[k_idle, k_om, k_exit],
                                   explanation=f"{s['name']}'s laptop was used in the incident, but they had left the building well before and had left the session open."))
            elif ro in ("plain", "bystander", "minor", "deleted", "loud"):
                if ro != "bystander" or True:
                    lock_t = (ex - 3) if ro != "bystander" else 21 * 60 + 55
                    self.log("DEVICE_LOG", lock_t, "HIGH", "device_lock", s["ref"], dev_of[s["ref"]], home[s["ref"]],
                             f"{self.nm(dev_of[s['ref']])} locked", self.dp(2), "exculpatory" if ro in ("loud", "deleted") else "noise")

        # ---- decoys
        if loud:
            ek = self.email(loud["ref"], [V["ref"]], f"{project}: credit for the results - this is not over",
                            16 * 60 + 42, f"{V['first']},\n\nYou presented my results as yours in front of the whole group. "
                            f"I will not let that stand. We settle this on Monday, one way or another.\n\n{loud['first']}",
                            "HIGH", self.dp(1), role="decoy",
                            data={"motive_for": loud["ref"], "motive_tag": "dispute", "motive_label": "Public dispute with the victim"})
            friend = r.choice([s for s in S if s is not loud and s is not perp])
            mk2 = self.msg(loud["ref"], friend["ref"], [
                (loud["ref"], 17 * 60 + 5, f"{V['first']} is going to regret taking my results."),
                (friend["ref"], 17 * 60 + 7, "Don't do anything stupid."),
                (loud["ref"], 17 * 60 + 8, "I'm not. But I'm not letting this slide either."),
            ], "MEDIUM", self.dp(2), "Heated exchange", role="decoy",
                data={"motive_for": loud["ref"], "motive_tag": "dispute", "motive_label": "Threatening message about the victim"})
            k_ret = self.ev("SYSTEM", f"Asset registry: {dec_serial} returned", 18 * 60 + 10, "HIGH",
                            [loud["ref"], ext, srv], f"{dec_serial} returned by {loud['name']} at 18:10",
                            self.dp(2), {"asset": {"serial": dec_serial, "person": loud["ref"], "action": "returned"},
                                         "text": f"Equipment record: {inc['ext_name']} {dec_serial} issued to {loud['name']} "
                                                 f"and returned 18:10."}, "exculpatory")
            exculp.append(k_ret)
            decoys.append(dict(kind="loud_motive", suspect=loud["ref"], evidence=[ek, mk2],
                               resolved_by=[x for x in exculp if x],
                               explanation=f"{loud['name']} had the loudest motive (a public credit dispute) but badged out before the incident and was seen leaving the garage."))
        if deleted:
            pol_k = self.ev("SYSTEM", "Retention policy RP-7 purge", tm - 14, "HIGH", [deleted["ref"], srv],
                            "Automatic purge of messages older than 6 hours for 14 accounts", self.dp(2),
                            {"text": f"Retention policy RP-7 executed at {fmt(tm - 14)}. Messages older than six hours were "
                                     f"deleted automatically for 14 accounts. Initiator: SYSTEM."}, "decoy_resolution")
            self.evt(tm - 14, "policy_purge", None, srv, "L-04", "Retention policy RP-7 executed (14 accounts)", pol_k)
            dk = self.log("DEVICE_LOG", tm - 14, "HIGH", "message_deleted", deleted["ref"], dev_of[deleted["ref"]],
                          home[deleted["ref"]], f"Message thread 'Re: weekend' deleted (account: {deleted['first'].lower()})",
                          self.dp(1), "decoy", data={"explained_by": pol_k})
            decoys.append(dict(kind="deleted_message", suspect=deleted["ref"], evidence=[dk], resolved_by=[pol_k],
                               explanation=f"The message deleted from {deleted['name']}'s account was removed by an automatic retention policy, not by a person."))
        if minor:
            ex = exit_m[minor["ref"]]
            mk3 = self.msg(minor["ref"], "Recruiter (Orchid Staffing)", [
                ("Recruiter (Orchid Staffing)", ex - 70, "Still good for the call tonight?"),
                (minor["ref"], ex - 66, "Yes, but not from the open office. I'll take it in the stairwell after hours."),
                ("Recruiter (Orchid Staffing)", ex - 65, "Perfect. Speak at 20:45."),
            ], "MEDIUM", self.dp(2), "Interview scheduling", role="decoy_resolution", ents=["L-01"])
            decoys.append(dict(kind="minor_lie", suspect=minor["ref"], evidence=[mk3],
                               explanation=f"{minor['name']} understated their departure time to hide a job interview call. It matters little: they had left the building long before the incident."))
        if bystander:
            ex = exit_m[bystander["ref"]]
            kb = self.log("ACCESS_LOG", tm - 14, "HIGH", "badge_room", bystander["ref"], badge, "L-04",
                          f"Badge entry: {bystander['name']} -> Server Room", self.dp(2), "decoy")
            kt = self.ev("SYSTEM", "Maintenance ticket MT-221", 18 * 60, "HIGH", [bystander["ref"], srv, "L-04"],
                         f"Server maintenance assigned to {bystander['name']}, 22:30-23:45", self.dp(2),
                         {"text": f"Ticket MT-221: scheduled server maintenance. Assigned: {bystander['name']}. Window 22:30-23:45."},
                         "decoy_resolution")
            decoys.append(dict(kind="bystander", suspect=bystander["ref"], evidence=[kb, kt],
                               explanation=f"{bystander['name']} was in the building during the incident, but in the server room on assigned maintenance, with no link to the incident device."))
        if self.P["tip"]:
            tgt = loud or owner or r.choice([s for s in S if s is not perp])
            kt = self.msg("Anonymous", V["ref"], [
                ("Anonymous", alert + 6, f"Check {tgt['name']}. They were around {self.nm(Lt)} tonight. I'm not signing this.")],
                "LOW", self.dp(1), "Anonymous tip", role="decoy",
                data={"claims": [{"person": tgt["ref"], "location_ref": Lt, "minute": tm - 5,
                                  "quote": f"{tgt['name']} near {self.nm(Lt)}"}]}, ents=[tgt["ref"]])
            decoys.append(dict(kind="anonymous_tip", suspect=tgt["ref"], evidence=[kt], resolved_by=exculp[:2],
                               explanation=f"The anonymous tip named {tgt['name']}, but badge and camera records place them outside the building."))
        if self.P["deceptive"] and loud:
            decoys.append(dict(kind="deceptive_witness", suspect=loud["ref"], evidence=[k_clean],
                               explanation=f"{W2['name']} falsely placed {loud['name']} in {self.nm(Lt)}; the badge exit and garage camera show {loud['name']} had left."))
        if self.P["early"]:
            cand = [s for s in S if s["ref"] in acl and s is not perp and s["ref"] != V["ref"]]
            if cand:
                x = r.choice(cand)
                kx = self.log("DEVICE_LOG", tm - 100, "HIGH", "server_access", x["ref"], srv, "L-04",
                              f"{fname} read from file server (account {x['first'].lower()})", self.dp(2), "decoy",
                              extra_ents=[file_ref])
                km = self.msg(x["ref"], V["ref"], [(x["ref"], tm - 98, f"Pulled the {inc['noun']} for the 22:00 review prep - all fine.")],
                              "MEDIUM", self.dp(2), "Review prep note", role="decoy_resolution", ents=[file_ref])
                decoys.append(dict(kind="earlier_access", suspect=x["ref"], evidence=[kx, km],
                                   explanation=f"{x['name']} legitimately read the {inc['noun']} earlier for review prep; this is a competing but harmless timeline."))

        # ---- noise
        for i in range(P["noise"]):
            a, b = r.sample(S, 2)
            t = r.choice(NOISE_CHATS)
            m0 = r.randint(10 * 60, 17 * 60)
            self.msg(a["ref"], b["ref"], [(a["ref"], m0, t[0]), (b["ref"], m0 + r.randint(1, 4), t[1])],
                     "MEDIUM", self.dp(1), "Routine chat", role="noise")
        self.log("DEVICE_LOG", 3 * 60, "HIGH", "system_job", None, srv, "L-04",
                 "Nightly patch window completed on NEX-SRV-01", self.dp(2), "noise")
        nf = [("project_notes.docx", "Document", "88 KB"), ("budget_q3.xlsx", "Spreadsheet", "412 KB")]
        extra_files = []
        for i, (fn, kind, size) in enumerate(nf):
            ow = r.choice(S)
            c = r.randint(9 * 60, 15 * 60)
            kf = self.ev("FILE", f"File: {fn}", c, "HIGH", [ow["ref"], f"F-{i+2:02d}", home[ow["ref"]]],
                         f"{fn} ({size}) owned by {ow['name']}", self.dp(2), {}, "noise")
            extra_files.append(dict(ref=f"F-{i+2:02d}", evidence_id=kf, filename=fn, created=c,
                                    modified=c + r.randint(10, 120), owner_ref=ow["ref"], size=size,
                                    location_ref=home[ow["ref"]], device_ref=dev_of[ow["ref"]],
                                    hash=self.hash(), access_history=[], extra={"target": False}))

        # ---- target file record
        created = r.randint(17 * 60 + 30, 18 * 60 + 15)
        hist = [{"minute": created, "who": V["name"], "action": "created", "device": srv, "evidence_id": None},
                {"minute": created + r.randint(15, 40), "who": V["name"], "action": "reviewed", "device": srv, "evidence_id": None},
                {"minute": tm - 2, "who": None, "action": "accessed", "device": dev, "evidence_id": k_access},
                {"minute": tm, "who": None, "action": "modified", "device": dev, "evidence_id": k_modify},
                {"minute": tm + 3, "who": None, "action": "transferred", "device": dev, "evidence_id": k_exta}]
        k_file = self.ev("FILE", f"File: {fname}", created, "HIGH", [file_ref, V["ref"], Lt, dev],
                         f"{fname} ({inc['size']}) - the affected asset", 1, {}, "context", init=True)
        tfile = dict(ref=file_ref, evidence_id=k_file, filename=fname, created=created, modified=tm, owner_ref=V["ref"],
                     size=inc["size"], location_ref=Lt, device_ref=dev, hash=self.hash(), access_history=hist,
                     extra={"target": True, "access_list": acl})
        files = [tfile] + extra_files
        for f in files:
            self.names[f["ref"]] = f["filename"]
        orgs = [dict(ref="ORG-1", name=comp, sub="employer")]
        if motive == "competitor":
            orgs.append(dict(ref="ORG-2", name=competitor, sub="competitor", derived=True))

        # ---- discovery
        total = len(self.evs)
        want = int(round(total * P["start"]))
        for e in self.evs:
            if e["init"]:
                continue
        have = sum(1 for e in self.evs if e["init"])
        cands = [e for e in self.evs if not e["init"] and e["depth"] == 1]
        r.shuffle(cands)
        for e in cands:
            if have >= want:
                break
            e["init"] = True
            have += 1

        truth_methods = {"own_workstation": f"Used their own authorized workstation ({dname}) to {inc['goal']}.",
                         "colleague_unlocked": f"Used {owner['name']}'s workstation ({dname}), left unlocked after {owner['first']} went home, to {inc['goal']}." if owner else "",
                         "shared_terminal": f"Used the shared lab terminal ({dname}) with no personal login, then removed the data on {serial}."}
        truth = dict(
            perpetrator_ref=perp["ref"], perpetrator_name=perp["name"], motive_key=motive, motive_label=MOTIVES[motive],
            method_key=method, method_label=METHODS[method], method_detail=truth_methods[method], minute=tm,
            time=fmt(tm), location_ref=Lt, location_name=self.nm(Lt), device_ref=dev, ext_serial=serial,
            owner_ref=owner["ref"] if owner else None, key_evidence=key, decoys=decoys, exculpatory=exculp,
            roles=self.roles, incident_key=inc_key, perp_exit=perp_exit, stated_departure=L_p,
        )
        # actual timeline (keys remapped later)
        truth["actual_timeline"] = [
            dict(minute=t_room, text=f"{perp['name']} badges into {self.nm(Lt)}", evidence_id=key[0]),
            dict(minute=tm - 7, text=ud, evidence_id=k_unlock),
            dict(minute=tm - 2, text=f"{fname} accessed", evidence_id=k_access),
            dict(minute=tm, text=f"{inc['modify']}", evidence_id=k_modify),
            dict(minute=tm + 2, text=f"{inc['connect']} ({serial})", evidence_id=k_extc),
            dict(minute=tm + 3, text=f"{inc['action']}", evidence_id=k_exta),
            dict(minute=perp_exit, text=f"{perp['name']} badges out of the building (stated departure: {fmt(L_p)})", evidence_id=k_pexit),
            dict(minute=alert, text="Integrity monitor raises the alert", evidence_id=alert_k),
        ]
        truth["actual_timeline"].sort(key=lambda t: t["minute"])

        case = dict(id=case_id_for(self.seed, self.diff), seed=self.seed, difficulty=self.diff, incident_type=inc_key,
                    title=inc["title"], case_number=2000 + int(self.seed.replace("-", ""), 16) % 999,
                    company=comp, summary=(f"At {fmt(alert)}, {comp}'s integrity monitor flagged an unexpected change to "
                                           f"{fname} (the {inc['noun']}). Badge logs, device telemetry, messages and witness "
                                           f"statements have been preserved. Establish who is responsible, why, and how."),
                    severity="CRITICAL" if inc_key in ("file_theft", "prototype_theft", "sabotage") else "HIGH",
                    incident_time=fmt(alert), alert_minute=alert, location_ref=Lt, status="ACTIVE", created_at=self.day,
                    data=dict(orgs=orgs, project=project, date=self.day, label=inc["label"],
                              knows=[[a["ref"], b["ref"], "friends"] for a, b in [r.sample(S, 2)]] if len(S) > 1 else []))
        for p in S + [V, W1, W2]:
            p.pop("first", None)
        bundle = dict(case=case, suspects=S, victims=[V], witnesses=[W1, W2], devices=D, locations=locs,
                      emails=self.emails, messages=self.messages, files=files, images=self.images,
                      events=self.events, evidence=self.evs, truth=truth)
        return self.finalize(bundle)

    def hash(self):
        return "-".join("%04X" % self.r.randrange(65536) for _ in range(4))

    # ---------------------------------------------------------------- motive evidence
    def motive_evidence(self, perp, motive, V, S, competitor, comp, project, tm, dom):
        r = self.r
        p = perp["ref"]
        d = lambda tag, label: {"motive_for": p, "motive_tag": tag, "motive_label": label}
        dd = self.dp(3, 0) if self.diff != "EASY" else 2
        out = []
        if motive == "financial":
            lender = r.choice(LENDERS)
            t = 13 * 60 + r.randint(0, 150)
            out.append(self.msg(p, f"{lender} (collections)", [
                (f"{lender} (collections)", t, "Final notice: your repayment plan lapses at month end. The guarantor will be contacted if the balance is not cleared."),
                (p, t + 14, "I need two more weeks. I'll have the full amount by then, I promise."),
            ], "MEDIUM", dd, "Overdue loan notice", role="key", data=d("financial", "Financial pressure: overdue loan notice")))
        elif motive == "rivalry":
            t = 14 * 60 + r.randint(0, 120)
            out.append(self.msg(p, "Ines (friend)", [
                (p, t, f"{V['name']} put their own name first on the {project} paper again."),
                ("Ines (friend)", t + 3, "After all those nights? That's rough."),
                (p, t + 5, "Years of work, and I'm a footnote. They have no idea what I could do with this data."),
            ], "MEDIUM", dd, "Venting about credit", role="key", data=d("rivalry", "Resentment over credit for the work")))
        elif motive == "competitor":
            rec = f"talent@{competitor.split()[0].lower()}.ext"
            out.append(self.email(rec, [p], "Following up on our conversation", 11 * 60 + r.randint(0, 120),
                                  f"Hello {perp['name'].split()[0]},\n\nThe offer we discussed stands, including the signing bonus. "
                                  f"As agreed, please bring the {project} materials with you on your first day - "
                                  f"that is what the team is most interested in.\n\n{competitor} Talent Team",
                                  "MEDIUM", dd, role="key", ents=[p], org="ORG-2", data=d("competitor", f"Offer from {competitor}")))
        elif motive == "revenge":
            t = 15 * 60 + r.randint(0, 90)
            out.append(self.msg(p, "Jo (friend)", [
                (p, t, "Passed over for lead again. After everything I did for this lab."),
                ("Jo (friend)", t + 2, "Maybe talk to HR?"),
                (p, t + 4, "HR won't help. They'll regret it by Monday."),
            ], "MEDIUM", dd, "Passed over for promotion", role="key", data=d("revenge", "Resentment over a denied promotion")))
        else:
            t = 19 * 60 + r.randint(0, 60)
            out.append(self.msg(p, "Unknown number", [
                ("Unknown number", t, "You have until midnight. Bring what we discussed or the photos go out."),
                (p, t + 6, "Please stop texting me. I'll do it."),
            ], "MEDIUM", dd, "Threatening messages", role="key", data=d("blackmail", "Pressured by an unknown party")))
        return out

    # ---------------------------------------------------------------- finalize
    def finalize(self, b):
        first = [e for e in self.evs if e["first"]]
        rest = sorted([e for e in self.evs if not e["first"]], key=lambda e: (e["minute"], e["order"]))
        idmap = {e["key"]: f"E-{i+1:03d}" for i, e in enumerate(first + rest)}
        for coll, prefix, width in ((self.emails, "EM", 2), (self.messages, "MS", 2), (self.images, "IM", 2)):
            for i, row in enumerate(sorted(coll, key=lambda x: (x["minute"], x["evidence_id"]))):
                row["ref"] = f"{prefix}-{i+1:02d}"
        self.events.sort(key=lambda e: (e["minute"], e["evidence_id"]))
        for i, e in enumerate(self.events):
            e["ref"] = f"EV-{i+1:04d}"
        for e in self.evs:
            e["id"] = e["key"]
        b = remap(b, idmap)
        day = self.day
        t = lambda m: f"{day} {fmt(m)}"
        by_ev = {}
        for coll in ("emails", "messages", "images", "files", "events"):
            for row in b[coll]:
                by_ev.setdefault(row["evidence_id"], row["ref"])
                if coll != "events":
                    by_ev[row["evidence_id"]] = row["ref"]
        for e in b["evidence"]:
            e["ts"] = t(e["minute"])
            e["source_ref"] = by_ev.get(e["id"])
            e["discovered"] = 1 if e.pop("init") else 0
            for k in ("key", "order", "first"):
                e.pop(k, None)
        b["evidence"].sort(key=lambda e: e["id"])
        for coll in ("emails", "messages", "images", "events"):
            for row in b[coll]:
                row["ts"] = t(row["minute"])
        b["truth"]["roles"] = {idmap.get(k, k): v for k, v in b["truth"]["roles"].items()}
        derive_relationships(b)
        derive_timeline(b)
        c = b["case"]
        c["data"]["counts"] = dict(suspects=len(b["suspects"]), devices=len(b["devices"]),
                                   evidence=len(b["evidence"]), locations=len(b["locations"]))
        return b


# -------------------------------------------------------------------- derivations
def derive_relationships(b):
    rels = []
    names = {p["ref"]: p["name"] for p in b["suspects"] + b["victims"] + b["witnesses"]}

    def R(src, dst, typ, minute=None, evid=None, label=""):
        if src and dst:
            rels.append(dict(ref=f"R-{len(rels)+1:04d}", src=src, dst=dst, type=typ, minute=minute,
                             evidence_id=evid, label=label))

    org = b["case"]["data"]["orgs"][0]["ref"]
    for p in b["suspects"] + b["victims"] + b["witnesses"]:
        R(p["ref"], org, "CONNECTED_TO", label="employee" if not p["ref"].startswith("W") else "staff")
    V = b["victims"][0]["ref"]
    for s in b["suspects"]:
        R(s["ref"], V, "WORKED_WITH", label="same project team")
    for a, c, lab in b["case"]["data"].get("knows", []):
        R(a, c, "KNOWS", label=lab)
    for d in b["devices"]:
        if d["owner_ref"]:
            R(d["owner_ref"], d["ref"], "USED", label="assigned")
        if d["location_ref"]:
            R(d["ref"], d["location_ref"], "LOCATED_AT", label="installed")
    for f in b["files"]:
        R(f["ref"], f["location_ref"], "LOCATED_AT", label="stored")
        R(f["owner_ref"], f["ref"], "CONNECTED_TO", label="owner")
    for e in b["events"]:
        t, ev, fm = e["type"], e["evidence_id"], fmt(e["minute"])
        tf = [f for f in b["files"] if f["extra"].get("target")][0]["ref"]
        if t == "badge_room":
            R(e["actor_ref"], e["location_ref"], "LOCATED_AT", e["minute"], ev, f"badge {fm}")
        elif t == "badge_out":
            R(e["actor_ref"], "L-01", "LOCATED_AT", e["minute"], ev, f"exit {fm}")
        elif t in ("device_unlock", "session_active"):
            R(e["actor_ref"], e["device_ref"], "USED", e["minute"], ev, f"login {fm}")
        elif t == "file_access":
            R(e["device_ref"], tf, "ACCESSED", e["minute"], ev, fm)
        elif t == "file_modify":
            R(e["device_ref"], e["ref"], "MODIFIED", e["minute"], ev, fm)
            R(e["ref"], tf, "MODIFIED", e["minute"], ev, fm)
        elif t == "ext_connect":
            ext = [d["ref"] for d in b["devices"] if d["kind"] == "external"][0]
            R(e["device_ref"], ext, "CONNECTED_TO", e["minute"], ev, fm)
        elif t == "ext_action":
            ext = [d["ref"] for d in b["devices"] if d["kind"] == "external"][0]
            R(ext, e["ref"], "TRANSFERRED", e["minute"], ev, fm)
            R(e["ref"], tf, "TRANSFERRED", e["minute"], ev, fm)
        elif t == "server_access":
            R(e["actor_ref"], tf, "ACCESSED", e["minute"], ev, f"read {fm}")
        elif t == "camera_detect":
            R(e["actor_ref"], e["location_ref"], "LOCATED_AT", e["minute"], ev, f"camera {fm}")
    for em in b["emails"]:
        if ISREF.match(em["sender"]):
            R(em["sender"], em["ref"], "EMAILED", em["minute"], em["evidence_id"], fmt(em["minute"]))
        for rc in em["recipients"]:
            if ISREF.match(rc):
                R(em["ref"], rc, "EMAILED", em["minute"], em["evidence_id"], fmt(em["minute"]))
        if (em.get("extra") or {}).get("org"):
            R(next((x for x in em["recipients"] if ISREF.match(x)), None), em["extra"]["org"], "CONNECTED_TO",
              em["minute"], em["evidence_id"], "recruited")
    for m in b["messages"]:
        for side in (m["a"], m["b"]):
            if ISREF.match(side):
                R(side, m["ref"], "MESSAGED", m["minute"], m["evidence_id"], fmt(m["minute"]))
    for im in b["images"]:
        R(im["ref"], im["location_ref"], "LOCATED_AT", im["minute"], im["evidence_id"], fmt(im["minute"]))
        R(im["ref"], im["device_ref"], "CONNECTED_TO", im["minute"], im["evidence_id"], "captured by")
    for ev in b["evidence"]:
        a = (ev.get("data") or {}).get("asset")
        if a:
            ext = [d["ref"] for d in b["devices"] if d["kind"] == "external"][0]
            R(a["person"], ext, "USED", ev["minute"], ev["id"], "checked out" if a["action"] == "checkout" else "returned")
    b["relationships"] = rels


def derive_timeline(b):
    rows = []
    covered = set()

    def T(minute, label, kind, typ, actors, dev, loc, evid):
        rows.append(dict(ref=None, minute=minute, ts=None, label=label, kind=kind, type=typ,
                         actors=[a for a in actors if a], device_ref=dev, location_ref=loc, evidence_id=evid))
        covered.add(evid)

    names = {p["ref"]: p["name"] for p in b["suspects"] + b["victims"] + b["witnesses"]}
    for e in b["events"]:
        T(e["minute"], e["description"], "event", e["type"], [e["actor_ref"]], e["device_ref"], e["location_ref"],
          e["evidence_id"])
    for em in b["emails"]:
        sn = names.get(em["sender"], em["sender"])
        T(em["minute"], f"Email from {sn}: {em['subject']}", "email", "email",
          [x for x in [em["sender"]] + em["recipients"] if ISREF.match(x)], (em.get("extra") or {}).get("origin_device")
          if str((em.get("extra") or {}).get("origin_device") or "").startswith("D-") else None, None, em["evidence_id"])
    for m in b["messages"]:
        T(m["minute"], f"Messages: {m['extra']['label']}", "message", "message",
          [x for x in (m["a"], m["b"]) if ISREF.match(x)], None, None, m["evidence_id"])
    for f in b["files"]:
        T(f["created"], f"File created: {f['filename']}", "file", "file_created", [f["owner_ref"]], f["device_ref"],
          f["location_ref"], f["evidence_id"])
    for ev in b["evidence"]:
        if ev["id"] not in covered and ev["type"] == "SYSTEM":
            T(ev["minute"], ev["title"], "system", "system", [], None, None, ev["id"])
    rows.sort(key=lambda r: (r["minute"], r["evidence_id"]))
    for i, r in enumerate(rows):
        r["ref"] = f"TL-{i+1:04d}"
        r["ts"] = f"{b['case']['data']['date']} {fmt(r['minute'])}"
    b["timeline_events"] = rows


# -------------------------------------------------------------------- public API
def generate_case(seed=None, difficulty="MEDIUM", ctype="RANDOM"):
    difficulty = difficulty.upper() if difficulty and difficulty.upper() in DIFF else "MEDIUM"
    seed = normalize_seed(seed)
    ctype = (ctype or "RANDOM").lower()
    last = None
    for attempt in range(60):
        b = Gen(seed, difficulty, ctype, attempt).build()
        last = b
        ok, report = case_director.validate(b)
        if ok:
            b["case"]["data"]["attempt"] = attempt
            return b
    return last

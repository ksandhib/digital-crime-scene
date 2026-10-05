"""Static content tables for the case generator. Everything here is fictional."""

FIRST = ["Marcus", "Mira", "Arin", "Elena", "Theo", "Priya", "Jonas", "Selene", "Daniel", "Yuki", "Rafael",
         "Naomi", "Idris", "Clara", "Tobias", "Anika", "Luca", "Imani", "Viktor", "Hana", "Owen", "Zara",
         "Felix", "Leila", "Caleb", "Mei", "Rohan", "Nadia", "Silas", "Ingrid"]
LAST = ["Vale", "Okafor", "Lindqvist", "Moreau", "Tanaka", "Brandt", "Castellan", "Whitlock", "Nakamura",
        "Ferreira", "Halloran", "Voss", "Delacroix", "Ibarra", "Sorensen", "Kapoor", "Mercer", "Ashby",
        "Petrov", "Quill", "Rennick", "Solano", "Thorne", "Underhill", "Varga", "Winslow", "Yamada", "Zeller",
        "Abara", "Corbin"]
ROLES = ["Research Engineer", "Project Lead", "Systems Administrator", "Data Scientist", "Lab Technician",
         "Security Analyst", "Finance Analyst", "Operations Manager", "Software Engineer", "Quality Auditor"]
COMPANIES = [("Nexora Labs", "nexora"), ("Auralis Research", "auralis"), ("Kestrel Biosystems", "kestrel"),
             ("Meridian Quantum", "meridian"), ("Obsidian Robotics", "obsidian")]
COMPETITORS = ["Helix Dynamics", "Vantor Systems", "Corvane Industries"]
PROJECTS = ["Project Lumen", "Project Halcyon", "Project Orion", "Project Tessera", "Project Vireo"]
LENDERS = ["Brightline Credit", "Harbor Finance", "Northgate Loans"]

LOCATIONS = [  # ref, name, building
    ("L-01", "Main Lobby", "HQ"),
    ("L-02", "Research Lab 3", "HQ"),
    ("L-03", "Research Office B", "HQ"),
    ("L-04", "Server Room", "HQ"),
    ("L-05", "Parking Garage", "Garage"),
    ("L-06", "Conference Room C", "HQ"),
]

INCIDENTS = {
    "file_theft": dict(
        label="Confidential file theft", title="CONFIDENTIAL RESEARCH FILE STOLEN", file="research_archive.dat",
        size="2.4 GB", ext_prefix="USB", ext_name="USB drive", connect="USB mass-storage device connected",
        action="Archive copied to external device", modify="Archive repackaged for export",
        goal="copy the research archive to an external drive", noun="research archive"),
    "sabotage": dict(
        label="Corporate sabotage", title="CORPORATE SABOTAGE - CALIBRATION DATA CORRUPTED",
        file="calibration_master.set", size="640 MB", ext_prefix="MTK", ext_name="Maintenance token",
        connect="Maintenance token inserted", action="Backup snapshot purged",
        modify="Calibration values overwritten", goal="overwrite the calibration data and purge its backup",
        noun="calibration data"),
    "missing_data": dict(
        label="Missing research data", title="MISSING RESEARCH DATA - TRIAL DATABASE EMPTIED",
        file="trial_results_q3.db", size="1.1 GB", ext_prefix="USB", ext_name="USB drive",
        connect="USB mass-storage device connected", action="Database exported, then purged",
        modify="Records marked for removal", goal="export and remove the Q3 trial database", noun="trial database"),
    "unauthorized_access": dict(
        label="Unauthorized system access", title="UNAUTHORIZED SYSTEM ACCESS - SECURE VAULT POLICY ALTERED",
        file="vault_index.cfg", size="18 MB", ext_prefix="SDG", ext_name="Service dongle",
        connect="Service dongle attached", action="Access policy exported",
        modify="Vault access policy edited", goal="alter the vault access policy and export it", noun="vault policy"),
    "fake_identity": dict(
        label="Fake identity investigation", title="FAKE IDENTITY INVESTIGATION - FORGED CONTRACTOR RECORD",
        file="contractor_registry.db", size="96 MB", ext_prefix="RIT", ext_name="Registry import token",
        connect="Registry import token presented", action="Registry entry committed under a forged profile",
        modify="Registry record inserted", goal="insert a forged contractor profile into the registry",
        noun="contractor registry"),
    "data_manipulation": dict(
        label="Data manipulation", title="DATA MANIPULATION - ASSAY RESULTS ALTERED", file="assay_results.csv",
        size="212 MB", ext_prefix="USB", ext_name="USB drive", connect="USB mass-storage device connected",
        action="Altered file copied to the review share", modify="Result columns altered",
        goal="alter the assay results before the review", noun="assay results"),
    "disappearing_files": dict(
        label="Disappearing project files", title="DISAPPEARING PROJECT FILES - ORION ARCHIVE EMPTIED",
        file="orion_project_files.zip", size="3.8 GB", ext_prefix="USB", ext_name="USB drive",
        connect="USB mass-storage device connected", action="Contents moved to external device",
        modify="Archive emptied", goal="move the project files off-site and empty the archive",
        noun="project archive"),
    "insider_activity": dict(
        label="Suspicious insider activity", title="SUSPICIOUS INSIDER ACTIVITY - PROJECT ASSIGNMENTS EDITED",
        file="personnel_projects.db", size="310 MB", ext_prefix="STG", ext_name="Staging drive",
        connect="Staging drive connected", action="Edit history exported",
        modify="Project assignments edited", goal="quietly edit project assignments and export the history",
        noun="assignment database"),
    "prototype_theft": dict(
        label="Research prototype theft", title="RESEARCH PROTOTYPE THEFT - BLUEPRINT PACKAGE TAKEN",
        file="prototype_blueprints.cad", size="4.6 GB", ext_prefix="USB", ext_name="USB drive",
        connect="USB mass-storage device connected", action="Package copied to external device",
        modify="Blueprint package re-exported", goal="copy the prototype blueprints to an external drive",
        noun="blueprint package"),
    "cyber_mystery": dict(
        label="Fictional cyber mystery", title="CYBER MYSTERY - SIGNAL LOGS REWRITTEN", file="signal_logs.bin",
        size="1.7 GB", ext_prefix="RLY", ext_name="Relay token", connect="Relay token connected",
        action="Rewritten segment exported", modify="Log segment rewritten",
        goal="rewrite the signal logs and export the original segment", noun="signal logs"),
}

METHODS = {
    "own_workstation": "Used their own authorized workstation",
    "colleague_unlocked": "Used a colleague's workstation that had been left unlocked",
    "shared_terminal": "Used the shared lab terminal and an unattributed session",
}

MOTIVES = {
    "financial": "Financial pressure",
    "rivalry": "Professional rivalry / credit dispute",
    "competitor": "Selling to a competitor",
    "revenge": "Resentment over a denied promotion",
    "blackmail": "Coerced by an outside party",
}

DIFF = {
    "EASY": dict(n=3, decoys=["loud"], methods=["own_workstation"], noise=2, start=0.5, margin=22,
                 dshift=-1, tip=False, early=False, deceptive=False, guard_clear=True),
    "MEDIUM": dict(n=4, decoys=["loud", "deleted"], methods=["own_workstation", "colleague_unlocked"], noise=3,
                   start=0.34, margin=18, dshift=0, tip=True, early=False, deceptive=False, guard_clear=True),
    "HARD": dict(n=5, decoys=["loud", "deleted", "minor"],
                 methods=["colleague_unlocked", "shared_terminal", "colleague_unlocked", "own_workstation"],
                 noise=4, start=0.26, margin=12, dshift=0, tip=True, early=True, deceptive=False,
                 guard_clear=True),
    "EXPERT": dict(n=6, decoys=["loud", "deleted", "minor", "bystander"],
                   methods=["colleague_unlocked", "shared_terminal"], noise=5, start=0.18, margin=10,
                   dshift=0, tip=True, early=True, deceptive=True, guard_clear=False),
}

NOISE_CHATS = [
    ("Did the calibration run finish before lunch?", "Yes, all green. I'll archive the logs tomorrow."),
    ("Are you joining the review on Friday?", "Wouldn't miss it. Can you send the slides ahead of time?"),
    ("Coffee machine on 2 is broken again.", "Facilities said Thursday. Use the one by the lab."),
    ("Can you cover my badge-in training tomorrow?", "Sure, send me the checklist."),
    ("Did you see the new parking rules?", "Garage level 2 is staff only now, apparently."),
    ("Reminder: expense reports are due this week.", "Thanks - nearly done with mine."),
]

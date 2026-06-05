"""
Known UK YouTubers with their government (Companies House) names and seed companies.
Seed company = a known company we can use to find their officer ID on Companies House.
"""

YOUTUBERS = [
    # ── The Sidemen ──────────────────────────────────────────────────────────
    {"name": "KSI",          "real_name": "Olajide Olatunji",                  "seed_company": "12129201", "surname": "OLATUNJI",  "group": "The Sidemen"},
    {"name": "Miniminter",   "real_name": "Simon Minter",                      "seed_company": "12129201", "surname": "MINTER",    "group": "The Sidemen"},
    {"name": "Zerkaa",       "real_name": "Joshua Bradley",                    "seed_company": "12129201", "surname": "BRADLEY",   "group": "The Sidemen", "extra_seed_companies": ["13834454"]},
    {"name": "TBJZL",        "real_name": "Tobit Brown",                       "seed_company": "12129201", "surname": "BROWN",     "group": "The Sidemen"},
    {"name": "W2S",          "real_name": "Harry Lewis",                       "seed_company": "12129201", "surname": "LEWIS",     "group": "The Sidemen", "extra_seed_companies": ["13568263"]},
    {"name": "Vikkstar123",  "real_name": "Vikram Barn",                       "seed_company": "12129201", "surname": "BARN",      "group": "The Sidemen", "extra_seed_companies": ["13697651"]},
    {"name": "Behzinga",     "real_name": "Ethan Payne",                       "seed_company": "12129201", "surname": "PAYNE",     "group": "The Sidemen"},

    # ── Beta Squad ───────────────────────────────────────────────────────────
    {"name": "Chunkz",       "real_name": "Amin Mohamed",                      "seed_company": "11999342", "surname": "MOHAMED",   "group": "Beta Squad", "extra_seed_companies": ["15341616"]},
    {"name": "Sharky",       "real_name": "Sharmarke Mohamud",                 "seed_company": "11999342", "surname": "MOHAMUD",   "group": "Beta Squad", "extra_seed_companies": ["15341616"]},
    {"name": "Niko Omilana", "real_name": "Nikolas Omilana",                   "seed_company": "11999342", "surname": "OMILANA",   "group": "Beta Squad", "extra_seed_companies": ["15341616"]},
    {"name": "AJ Shabeel",   "real_name": "Ayaanle Shabeel",                   "seed_company": "11999342", "surname": "SHABEEL",   "group": "Beta Squad", "extra_seed_companies": ["15341616"]},
    {"name": "KingKenny",    "real_name": "Kenny Ojuederie",                   "seed_company": "11999342", "surname": "OJUEDERIE", "group": "Beta Squad", "extra_seed_companies": ["15341616"]},

    # ── Sidemen Orbit ─────────────────────────────────────────────────────
    {"name": "Calfreezy",    "real_name": "Callum Airey",                      "seed_company": "13054703", "surname": "AIREY",     "group": "Sidemen Orbit", "extra_seed_companies": ["09711376"]},
    {"name": "Callux",       "real_name": "Callum Aaron McGinley",             "seed_company": "12512852", "surname": "MCGINLEY",  "group": "Sidemen Orbit", "extra_seed_companies": ["10451833"]},
    {"name": "ChrisMD",      "real_name": "Christopher Dixon",                 "seed_company": "13427413", "surname": "DIXON",     "group": "Sidemen Orbit"},
    {"name": "Stephen Tries","real_name": "Stephen Lawson",                    "seed_company": "11578506", "surname": "LAWSON",    "group": "Sidemen Orbit"},
    {"name": "Reev",         "real_name": "Oliver Fletcher-Warrington",        "seed_company": "10108561", "surname": "FLETCHER",  "group": "Sidemen Orbit"},
    {"name": "TheBurntChip", "real_name": "Joshua Larkin",                     "seed_company": "13054703", "surname": "LARKIN",    "group": "Sidemen Orbit"},
    {"name": "Randolph",     "real_name": "Andrew John Shane",                 "seed_company": "11846410", "surname": "SHANE",     "group": "Sidemen Orbit"},
    {"name": "Theo Baker",   "real_name": "Theodore Philip Thomas Baker",      "seed_company": "10518815", "surname": "BAKER",     "group": "Sidemen Orbit"},
    {"name": "Deji",         "real_name": "Oladeji Olatunji",                  "seed_company": "08208163", "surname": "OLATUNJI",  "group": "Sidemen Orbit"},
    {"name": "WillNE",       "real_name": "William Jonathan Lenney",           "seed_company": "10546302", "surname": "LENNEY",    "group": "Sidemen Orbit"},
    {"name": "Danny Aarons", "real_name": "Daniel Peter Aarons",               "seed_company": "14121151", "surname": "AARONS",    "group": "Sidemen Orbit"},

    # ── Friends from Work ────────────────────────────────────────────────
    {"name": "George Clarke","real_name": "George Clarke",                     "seed_company": "17047852", "surname": "CLARKE",    "group": "Friends from Work"},
    {"name": "ArthurTV",     "real_name": "Arthur Frederick Lanzon Fern",      "seed_company": "17047852", "surname": "FERN",      "group": "Friends from Work"},
    {"name": "Arthur Hill",  "real_name": "Arthur Nicholas Finch Hill",        "seed_company": "17047852", "surname": "HILL",      "group": "Friends from Work"},
    {"name": "Italian Bach", "real_name": "Isaac Craven Smith",                "seed_company": "17047852", "surname": "SMITH",     "group": "Friends from Work"},

    # ── Other UK YouTubers ───────────────────────────────────────────────
    {"name": "Max Fosh",         "real_name": "Maximilian Arthur Fosh",        "seed_company": "12069656", "surname": "FOSH",      "group": "Other UK YouTubers"},
    {"name": "AB",               "real_name": "Alfie Noah Buttle",             "seed_company": "16166511", "surname": "BUTTLE",    "group": "Other UK YouTubers"},
    {"name": "MrWho'sTheBoss",   "real_name": "Arun Maini",                    "seed_company": "11130068", "surname": "MAINI",     "group": "Other UK YouTubers"},

    # ── The Bov Boys ─────────────────────────────────────────────────────
    {"name": "Angry Ginge",  "real_name": "Morgan Sam Lee Burtwistle",         "seed_company": "16628776", "surname": "BURTWISTLE","group": "The Bov Boys"},
    {"name": "Heinzbains",   "real_name": "Ryan McCaul",                       "seed_company": "16628776", "surname": "MCCAUL",    "group": "The Bov Boys"},
    {"name": "Tayz",         "real_name": "Michael Joseph Taylor",             "seed_company": "16628776", "surname": "TAYLOR",    "group": "The Bov Boys"},
]

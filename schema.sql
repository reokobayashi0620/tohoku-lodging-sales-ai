CREATE TABLE IF NOT EXISTS facilities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL, company_name TEXT DEFAULT '', prefecture TEXT NOT NULL, city TEXT DEFAULT '',
  address TEXT DEFAULT '', facility_type TEXT DEFAULT '', official_url TEXT DEFAULT '', phone TEXT DEFAULT '', email TEXT DEFAULT '',
  contact_url TEXT DEFAULT '', pet_friendly INTEGER NOT NULL DEFAULT 0, whole_house INTEGER NOT NULL DEFAULT 0,
  multiple_facilities INTEGER NOT NULL DEFAULT 0, wood_floor INTEGER NOT NULL DEFAULT 0,
  source_url TEXT DEFAULT '', notes TEXT DEFAULT '', priority TEXT NOT NULL DEFAULT 'C',
  priority_reason TEXT DEFAULT '', status TEXT NOT NULL DEFAULT '未連絡',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lead_candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT DEFAULT '', company_name TEXT DEFAULT '', prefecture TEXT NOT NULL, city TEXT DEFAULT '', address TEXT NOT NULL,
  official_url TEXT DEFAULT '', phone TEXT DEFAULT '', email TEXT DEFAULT '', contact_url TEXT DEFAULT '',
  pet_friendly INTEGER NOT NULL DEFAULT 0, whole_house INTEGER NOT NULL DEFAULT 0,
  multiple_facilities INTEGER NOT NULL DEFAULT 0, wood_floor INTEGER NOT NULL DEFAULT 0,
  research_status TEXT NOT NULL DEFAULT 'unresearched', research_notes TEXT DEFAULT '',
  source_url TEXT DEFAULT '', source_type TEXT DEFAULT '',
  normalized_key TEXT NOT NULL UNIQUE, status TEXT NOT NULL DEFAULT 'pending',
  matched_facility_id INTEGER,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (matched_facility_id) REFERENCES facilities(id)
);

CREATE INDEX IF NOT EXISTS idx_lead_candidates_status ON lead_candidates(status);
CREATE INDEX IF NOT EXISTS idx_lead_candidates_research_status ON lead_candidates(research_status);

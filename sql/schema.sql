-- Twin-2K-500 SQLite schema. See docs/SCHEMA.md.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS personas (
    persona_id TEXT PRIMARY KEY NOT NULL,
    persona_summary TEXT NOT NULL,
    region TEXT,
    gender TEXT,
    age_band TEXT,
    education_level TEXT,
    race TEXT,
    us_citizen INTEGER CHECK (us_citizen IN (0, 1)),
    marital_status TEXT,
    religion TEXT,
    religious_attendance TEXT,
    political_affiliation TEXT,
    income_band TEXT,
    political_views TEXT,
    household_size INTEGER,
    employment_status TEXT,
    loaded_at TEXT NOT NULL DEFAULT (datetime('now')),
    source_revision TEXT
);

CREATE INDEX IF NOT EXISTS idx_personas_region_education
    ON personas (region, education_level);
CREATE INDEX IF NOT EXISTS idx_personas_age_income
    ON personas (age_band, income_band);

CREATE TABLE IF NOT EXISTS questions (
    item_id TEXT PRIMARY KEY NOT NULL,
    question_id TEXT NOT NULL,
    sub_id TEXT,
    question_text TEXT,
    item_text TEXT,
    question_type TEXT,
    options_json TEXT,
    is_overlap INTEGER NOT NULL DEFAULT 0 CHECK (is_overlap IN (0, 1)),
    category TEXT
);

CREATE INDEX IF NOT EXISTS idx_questions_qid ON questions (question_id);
CREATE INDEX IF NOT EXISTS idx_questions_overlap ON questions (is_overlap);

CREATE TABLE IF NOT EXISTS answers_wave1_3 (
    persona_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    value_numeric REAL,
    value_label TEXT,
    PRIMARY KEY (persona_id, item_id),
    FOREIGN KEY (persona_id) REFERENCES personas (persona_id),
    FOREIGN KEY (item_id) REFERENCES questions (item_id)
);

CREATE INDEX IF NOT EXISTS idx_answers_w13_item ON answers_wave1_3 (item_id);
CREATE INDEX IF NOT EXISTS idx_answers_w13_persona ON answers_wave1_3 (persona_id);

CREATE TABLE IF NOT EXISTS answers_wave4 (
    persona_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    value_numeric REAL,
    value_label TEXT,
    PRIMARY KEY (persona_id, item_id),
    FOREIGN KEY (persona_id) REFERENCES personas (persona_id),
    FOREIGN KEY (item_id) REFERENCES questions (item_id)
);

CREATE INDEX IF NOT EXISTS idx_answers_w4_item ON answers_wave4 (item_id);
CREATE INDEX IF NOT EXISTS idx_answers_w4_persona ON answers_wave4 (persona_id);

CREATE VIEW IF NOT EXISTS answers_current AS
SELECT a.persona_id, a.item_id, a.value_numeric, a.value_label, '4' AS source_wave
FROM answers_wave4 AS a
JOIN questions AS q ON q.item_id = a.item_id
WHERE q.is_overlap = 1

UNION ALL

SELECT a.persona_id, a.item_id, a.value_numeric, a.value_label, '1-3' AS source_wave
FROM answers_wave1_3 AS a
JOIN questions AS q ON q.item_id = a.item_id
WHERE q.is_overlap = 0;

-- Simulation campaigns, questions, and simulation runs.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY,
    name TEXT,
    description TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    is_saved INTEGER NOT NULL DEFAULT 0 CHECK (is_saved IN (0, 1))
);

CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY,
    question_name TEXT,
    question_type TEXT,
    instructions TEXT,
    criteria TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    is_saved INTEGER NOT NULL DEFAULT 0 CHECK (is_saved IN (0, 1))
);

CREATE TABLE IF NOT EXISTS campaign_questions (
    campaign_id INTEGER NOT NULL,
    question_id INTEGER NOT NULL,
    PRIMARY KEY (campaign_id, question_id),
    FOREIGN KEY (campaign_id) REFERENCES campaigns (id),
    FOREIGN KEY (question_id) REFERENCES questions (id)
);

CREATE TABLE IF NOT EXISTS simulations (
    simulation_id INTEGER PRIMARY KEY,
    simulation_name TEXT,
    model_name TEXT,
    status TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS simulation_campaigns (
    simulation_id INTEGER NOT NULL,
    campaign_id INTEGER NOT NULL,
    PRIMARY KEY (simulation_id, campaign_id),
    FOREIGN KEY (simulation_id) REFERENCES simulations (simulation_id),
    FOREIGN KEY (campaign_id) REFERENCES campaigns (id)
);

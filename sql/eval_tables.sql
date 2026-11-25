-- Eval runs and wave 4 predictions.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS eval_runs (
    eval_id INTEGER PRIMARY KEY,
    name TEXT,
    model_name TEXT,
    persona_limit INTEGER,
    status TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    accuracy REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS eval_wave4_predictions (
    eval_id INTEGER NOT NULL,
    persona_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    predicted TEXT,
    probabilities TEXT,
    actual_label TEXT,
    PRIMARY KEY (eval_id, persona_id, item_id),
    FOREIGN KEY (eval_id) REFERENCES eval_runs (eval_id)
);

PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS questions;
DROP TABLE IF EXISTS reactions;

CREATE TABLE questions (
    category TEXT NOT NULL CHECK (category IN ('noul', 'choice', 'score')),
    campaign TEXT NOT NULL,
    instructions_json TEXT,
    criteria_json TEXT,
    CHECK (
        (
            category = 'score'
            AND instructions_json IS NULL
            AND criteria_json IS NULL
        )
        OR (
            category IN ('noul', 'choice')
            AND instructions_json IS NOT NULL
            AND criteria_json IS NOT NULL
        )
    )
);

CREATE TABLE reactions (
    name TEXT PRIMARY KEY,
    instructions_json TEXT NOT NULL,
    criteria_json TEXT NOT NULL
);

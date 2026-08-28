-- Optional SQLite schema for M3

CREATE TABLE IF NOT EXISTS track_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    message_seq INTEGER,
    track_sequence_no INTEGER,
    lat REAL,
    lon REAL,
    altitude REAL,
    alt_type TEXT,
    speed REAL,
    heading REAL,
    vertical_rate REAL,
    on_ground INTEGER,
    callsign TEXT,
    timestamp_source TEXT,
    message_valid INTEGER
);

CREATE INDEX IF NOT EXISTS idx_track_target_time ON track_records(target_id, timestamp);

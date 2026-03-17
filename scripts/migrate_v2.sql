-- LeagueSpy v2 Migration
-- Run after initial setup_db.sql

-- Streak tracking on summoners
ALTER TABLE summoners ADD (
    current_streak NUMBER DEFAULT 0,
    longest_win_streak NUMBER DEFAULT 0,
    longest_loss_streak NUMBER DEFAULT 0
);

-- Track live game detection state
CREATE TABLE live_games (
    summoner_id NUMBER PRIMARY KEY REFERENCES summoners(id),
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    champion VARCHAR2(50),
    game_mode VARCHAR2(30)
);

-- Store generated roasts to avoid repetition
CREATE SEQUENCE roast_history_seq START WITH 1 INCREMENT BY 1;

CREATE TABLE roast_history (
    id NUMBER DEFAULT roast_history_seq.NEXTVAL PRIMARY KEY,
    summoner_id NUMBER NOT NULL REFERENCES summoners(id),
    match_id VARCHAR2(50),
    roast_text VARCHAR2(1000) NOT NULL,
    trigger_type VARCHAR2(30),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

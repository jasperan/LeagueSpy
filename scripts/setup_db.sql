-- LeagueSpy Oracle Database Setup
-- Run as: leaguespy/leaguespy@localhost:1523/FREEPDB1
--
-- Usage (via sqlplus):
--   sqlplus leaguespy/leaguespy@localhost:1523/FREEPDB1 @scripts/setup_db.sql
--
-- Or let the application create tables automatically via database.py

CREATE SEQUENCE summoners_seq START WITH 1 INCREMENT BY 1;
CREATE SEQUENCE matches_seq START WITH 1 INCREMENT BY 1;

CREATE TABLE summoners (
    id NUMBER DEFAULT summoners_seq.NEXTVAL PRIMARY KEY,
    player_name VARCHAR2(100) NOT NULL,
    summoner_slug VARCHAR2(100) NOT NULL,
    region VARCHAR2(10) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_summoner UNIQUE (summoner_slug, region)
);

CREATE TABLE matches (
    id NUMBER DEFAULT matches_seq.NEXTVAL PRIMARY KEY,
    summoner_id NUMBER NOT NULL REFERENCES summoners(id),
    match_id VARCHAR2(50) NOT NULL,
    champion VARCHAR2(50) NOT NULL,
    win NUMBER(1) NOT NULL,
    kills NUMBER NOT NULL,
    deaths NUMBER NOT NULL,
    assists NUMBER NOT NULL,
    game_duration VARCHAR2(20),
    game_mode VARCHAR2(30),
    played_at VARCHAR2(30),
    announced NUMBER(1) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_match UNIQUE (summoner_id, match_id)
);

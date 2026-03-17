-- LeagueSpy v3 Migration: enhanced match details
ALTER TABLE matches ADD (
    cs NUMBER DEFAULT 0,
    gold NUMBER DEFAULT 0,
    kill_participation NUMBER DEFAULT 0,
    vision_score NUMBER DEFAULT 0,
    match_url VARCHAR2(200)
);

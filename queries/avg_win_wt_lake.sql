SELECT
    t.lake,
    COUNT(DISTINCT t.id) AS tournament_count,
    ROUND(AVG(r.weight), 2) AS avg_winning_weight
FROM tournaments t
JOIN results r ON t.id = r.tournament_id
WHERE r.place = 1 AND t.lake IS NOT NULL AND r.weight IS NOT NULL
GROUP BY t.lake
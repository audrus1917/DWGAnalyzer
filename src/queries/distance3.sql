SELECT 
    COUNT(*)
FROM 
    entity AS b
JOIN
    entity AS a ON ST_Intersects(a.geom, b.geom)
WHERE a.id = 2397553

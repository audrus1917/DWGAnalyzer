SELECT 
    b.id,
    b.entity_type,
    b.description
FROM 
    entity AS b
JOIN
    entity AS a ON ST_Intersects(a.geom, b.geom)
WHERE a.id = 422755
LIMIT 100

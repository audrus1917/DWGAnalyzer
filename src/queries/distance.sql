SELECT 
    b.id,
    b.entity_type,
    b.name,
    b.description,
    ST_AsText(b.geom),
FROM 
    entity AS b
JOIN
    entity AS a ON a.geom is not null AND ST_Intersects(a.geom, b.geom)
WHERE a.id = 422755 
LIMIT 10;

SELECT 
    b.id,
    b.entity_type,
    b.name,
    b.description,
    ST_AsText(b.geom),
    ST_Distance(b.geom, a.geom) as dist
FROM 
    entity AS b
JOIN
    entity AS a ON true
WHERE a.id = 1525955
ORDER BY 
    a.geom <-> b.geom
LIMIT 100;

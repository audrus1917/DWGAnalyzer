SELECT 
    b.id,
    b.name,
    b.entity_type,
    b.data,
    ST_Distance(b.geom, a.geom)
FROM 
    entity AS b
JOIN
    entity AS a ON true
WHERE a.id = 2586945
ORDER BY 5 
LIMIT 100

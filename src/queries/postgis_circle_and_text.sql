SELECT 
    c.entity_type, c.name, a.id, a.name, a.description, b.id, b.name, ST_Distance(a.geom, b.geom) as distance, b.data->'radius' AS radius
FROM
    entity AS a 
    INNER JOIN entity AS c ON a.parent_id = c.id
    INNER JOIN entity AS b ON ST_DWithin(a.geom, b.geom, CAST(b.data->'radius' AS float))
WHERE (a.entity_type = 'TEXT' or a.entity_type = 'MTEXT')
    AND b.entity_type = 'CIRCLE'
    AND CAST(b.data->'radius' AS float) = 500
LIMIT 1000
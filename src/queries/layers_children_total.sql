SELECT
    COUNT(*) AS primitive_count,
    e.entity_type AS primitive_type,
    l.id AS layer_id
FROM entity_to_entity AS ee
INNER JOIN entity AS e ON e.id = ee.src_id
INNER JOIN entity AS l ON l.id = ee.dst_id
WHERE l.entity_type = 'LAYER'
GROUP BY l.id, e.entity_type
ORDER BY primitive_count DESC
LIMIT 10;
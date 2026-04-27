SELECT
    COUNT(DISTINCT l.id) AS layers_count,
    p.id AS block_id
FROM entity AS p
INNER JOIN entity AS e ON e.parent_id = p.id
INNER JOIN entity_to_entity AS ee ON ee.src_id = e.id
INNER JOIN entity AS l ON l.id = ee.dst_id
WHERE 
    l.entity_type = 'LAYER'
    AND p.entity_type = 'BLOCK'
GROUP BY p.id
ORDER BY layers_count DESC
LIMIT 10;
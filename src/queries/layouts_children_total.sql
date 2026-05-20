-- Количество "детей" для `LAYOUT`-ов, сгруппированное по имени родителя

SELECT
    COUNT(c.id) AS total_children,
    p.name AS parent_name
FROM entity AS p
LEFT JOIN entity AS c ON c.parent_id = p.id
WHERE p.entity_type = 'LAYOUT'::EntityType
GROUP BY 2
-- Суммарная площадь штриховки `ZIGZAG` для каждого `LAYOUT`

SELECT
    COUNT(*) AS total_hatches,
    SUM((hatch.data->>'area')::numeric) AS total_hatch_area,
    layout.name AS layout_name
FROM entity AS hatch
JOIN entity AS layout ON hatch.parent_id = layout.id AND layout.entity_type = 'LAYOUT'::EntityType
WHERE hatch.name = 'ZIGZAG'
GROUP BY layout.name
ORDER BY total_hatch_area DESC;
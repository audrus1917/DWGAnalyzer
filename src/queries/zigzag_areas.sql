-- Суммарная площадь штриховки `ZIGZAG` для каждого `LAYOUT`

SELECT
    (hatch.data->>'area')::numeric / 1000000 AS hatch_area,
    layout.name AS layout_name
FROM entity AS hatch
JOIN entity AS layout ON hatch.parent_id = layout.id AND layout.entity_type = 'LAYOUT'::EntityType
WHERE hatch.name = 'ZIGZAG'
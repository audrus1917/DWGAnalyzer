-- Суммарная площадь штриховки `ZIGZAG` для каждого `LAYOUT`

SELECT
    c.name,
    c.parent_id
FROM entity AS c
WHERE c.name = 'ZIGZAG'


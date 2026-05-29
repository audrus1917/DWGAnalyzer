-- Поиск полилинии и штриховки для "Деформационного шва"

SELECT 
    c.id
    ,
    c.name,
    c.entity_type,
    c.data->'area' AS area,
    ST_AsText(c.geom)
FROM entity AS c
WHERE 
    CAST(c.data->>'area' AS float) > 9094123
    AND CAST(c.data->>'area' AS float) < 9095000

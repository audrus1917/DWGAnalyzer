-- Количество сущностей `INSERT`, которые не имеют атрибуты

WITH blocks_with_attribs AS (
    SELECT 
        id
    FROM entity 
    WHERE data ? 'attribs' 
        AND entity_type = 'INSERT' 
)

SELECT
    COUNT(*)
FROM entity AS a
LEFT JOIN entity AS b ON b.id = a.id AND b.entity_type = 'INSERT'
WHERE
    a.entity_type = 'INSERT'
    AND b.id IN NULL

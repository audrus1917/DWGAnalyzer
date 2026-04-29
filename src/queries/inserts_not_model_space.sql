-- Количество сущностей `INSERT`, которые имеют атрибуты

SELECT 
    COUNT(*)
FROM entity 
WHERE data ? 'attribs' 
    AND entity_type = 'INSERT' 
    AND data->'attribs'->>'parent_block' != '*Model_Space'
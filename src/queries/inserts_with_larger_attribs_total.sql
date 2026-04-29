-- Количество сущностей `INSERT`, которые имеют атрибуты

SELECT 
    COUNT(*), 
    data->'block' AS block_name
FROM entity 
WHERE data ? 'attribs' 
    AND entity_type = 'INSERT' 
GROUP BY 2 
ORDER BY 1 DESC
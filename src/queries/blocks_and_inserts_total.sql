WITH blocks_inserts AS (
    SELECT 
        COUNT(*) AS total, 
        parent_id 
    FROM entity 
    WHERE entity_type = 'INSERT' 
    GROUP BY 2
)

SELECT 
    a.id, 
    a.name,
    b.total
FROM entity AS a 
INNER JOIN blocks_inserts AS b ON b.parent_id = a.id
ORDER BY 3 DESC
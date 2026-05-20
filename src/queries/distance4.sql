SELECT 
    ST_Distance(b.geom, a.geom)
FROM 
    entity AS b
JOIN
    entity AS a ON a.id = 2586945
WHERE b.id = 2588701
 

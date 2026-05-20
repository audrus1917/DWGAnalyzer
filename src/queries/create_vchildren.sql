CREATE VIEW vchildren AS 
SELECT
    c.id,
    c.entity_type,
    c.name,
    c.description,
    c.parent_id,
    p.entity_type AS p_entity_type,
    p.name AS parent_name
FROM entity AS c
JOIN entity AS p ON c.parent_id = p.id
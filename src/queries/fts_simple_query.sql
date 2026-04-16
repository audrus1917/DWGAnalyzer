-- Пример "наивного" полнотекстового поиска 

SELECT id, name, ts_rank(to_tsvector(name), plainto_tsquery('РУБЕЖ'))
FROM entity
WHERE to_tsvector(name) @@ plainto_tsquery('РУБЕЖ')
ORDER BY ts_rank(to_tsvector(name), plainto_tsquery('РУБЕЖ')) DESC;
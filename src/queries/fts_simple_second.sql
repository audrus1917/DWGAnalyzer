-- Пример "наивного" полнотекстового поиска 

SELECT id, name, data, ts_rank(to_tsvector(data::text), plainto_tsquery('РУБЕЖ'))
FROM entity
WHERE to_tsvector(data::text) @@ plainto_tsquery('РУБЕЖ')
ORDER BY ts_rank(to_tsvector(data::text), plainto_tsquery('РУБЕЖ')) DESC;
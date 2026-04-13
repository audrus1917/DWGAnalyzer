Мне нужно добавить:

* работу с БД PostgreSQL через SQLAlchemy. DSN для БД - asyncpg://andrus@localhost:5432/parsedwg_db
* для нее добавить pgvector для дальнейшего использования RAG
* модель данных основная - Entity
  - id
  - name 
  - description
  - entity_type (folder, file, zipfile, zipped_file, block, layout, layer, primitive)
  - data
  - created_at
  - created_by
  - updated_at
  - updated_by
  - start_from

* EntityToEntity - связи между сущностями

  - src
  - dst
  - link (contains, related etc)

 


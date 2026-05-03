curl -X "POST" https://ollama.com/api/chat   -H "Authorization: Bearer 2bdb01952c7046208b30adc772cc3813.hbvqAMmhajB8k3Nv34StY2Su"   -d '{
    "model": "gpt-oss:120b",
    "messages": [{
      "role": "user",
      "content": "Выдели основную категорию объекта.\n\nНаименование: Дренаж 4_22-12-2023\nСлои:{\"layer\": \"M_Drainage\"}"
    }],
    "stream": false
  }'
  
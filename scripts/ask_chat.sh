#!/bin/bash

curl http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3.1:8b",
    "messages": [
      {
        "role": "system",
        "content": "Ты — инженер-проектировщик. Отвечай кратко, тезисно, используя терминологию ГОСТ."
      },
      {
        "role": "user",
        "content": "Разбери название блока: \"Ограждение - Ограждение-71499671-План 4 этажа на отм_ _17_460\""
      }
    ],
    "temperature": 0.1
  }'

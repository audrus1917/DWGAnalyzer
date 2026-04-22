from __future__ import annotations

import json
import os
import uuid
from typing import Iterator

import redis

type JobEntry = dict[str, str]

_TTL_SECONDS = 86_400  # 24 часа

_KEY_SOURCES = "parsedwg:sources:{job_id}"
_KEY_CONVERTED = "parsedwg:converted:{job_id}"


def _get_redis() -> redis.Redis:
    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    return redis.Redis.from_url(url, decode_responses=True)


def new_job_id() -> str:
    return uuid.uuid4().hex


def push_sources(job_id: str, entries: list[JobEntry]) -> None:
    r = _get_redis()
    key = _KEY_SOURCES.format(job_id=job_id)
    pipe = r.pipeline()
    for entry in entries:
        pipe.rpush(key, json.dumps(entry, ensure_ascii=False))
    pipe.expire(key, _TTL_SECONDS)
    pipe.execute()


def load_sources(job_id: str) -> list[JobEntry]:
    r = _get_redis()
    key = _KEY_SOURCES.format(job_id=job_id)
    return [json.loads(item) for item in r.lrange(key, 0, -1)]


def push_converted(job_id: str, entry: JobEntry) -> None:
    r = _get_redis()
    key = _KEY_CONVERTED.format(job_id=job_id)
    pipe = r.pipeline()
    pipe.rpush(key, json.dumps(entry, ensure_ascii=False))
    pipe.expire(key, _TTL_SECONDS)
    pipe.execute()


def load_converted(job_id: str) -> list[JobEntry]:
    r = _get_redis()
    key = _KEY_CONVERTED.format(job_id=job_id)
    return [json.loads(item) for item in r.lrange(key, 0, -1)]


def iter_converted(job_id: str) -> Iterator[JobEntry]:
    yield from load_converted(job_id)


def delete_job(job_id: str) -> None:
    r = _get_redis()
    r.delete(
        _KEY_SOURCES.format(job_id=job_id),
        _KEY_CONVERTED.format(job_id=job_id),
    )


__all__ = [
    "new_job_id",
    "push_sources",
    "load_sources",
    "push_converted",
    "load_converted",
    "iter_converted",
    "delete_job",
]

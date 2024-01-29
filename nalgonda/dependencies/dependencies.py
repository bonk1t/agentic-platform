from fastapi import Depends
from redis import asyncio as aioredis

from nalgonda.repositories.agency_config_firestore_storage import AgencyConfigFirestoreStorage
from nalgonda.repositories.agent_config_firestore_storage import AgentConfigFirestoreStorage
from nalgonda.services.agency_manager import AgencyManager
from nalgonda.services.agent_manager import AgentManager
from nalgonda.services.caching.redis_cache_manager import RedisCacheManager
from nalgonda.services.thread_manager import ThreadManager
from nalgonda.settings import settings


def get_redis() -> aioredis.Redis:
    redis_url = str(settings.redis_tls_url or settings.redis_url)
    redis = aioredis.from_url(redis_url, decode_responses=False, ssl_cert_reqs="none")
    return redis


def get_redis_cache_manager(redis: aioredis.Redis = Depends(get_redis)) -> RedisCacheManager:
    return RedisCacheManager(redis)


def get_agent_manager(storage: AgentConfigFirestoreStorage = Depends(AgentConfigFirestoreStorage)) -> AgentManager:
    return AgentManager(storage)


def get_agency_manager(
    cache_manager: RedisCacheManager = Depends(get_redis_cache_manager),
    agent_manager: AgentManager = Depends(get_agent_manager),
    agency_config_storage: AgencyConfigFirestoreStorage = Depends(AgencyConfigFirestoreStorage),
) -> AgencyManager:
    return AgencyManager(cache_manager, agent_manager, agency_config_storage)


def get_thread_manager() -> ThreadManager:
    """Returns a ThreadManager object"""
    return ThreadManager()

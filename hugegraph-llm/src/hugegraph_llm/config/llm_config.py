# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.


from typing import ClassVar, Literal, Optional

from .models import BaseConfig


class LLMConfig(BaseConfig):
    """LLM settings"""

    _config_section: ClassVar[str] = "llm"
    _flat_to_nested_mapping: ClassVar[dict[str, str]] = {
        "language": "language",
        "chat_llm_type": "chat_llm_type",
        "extract_llm_type": "extract_llm_type",
        "text2gql_llm_type": "text2gql_llm_type",
        "embedding_type": "embedding_type",
        "reranker_type": "reranker.type",
        "keyword_extract_type": "keyword_extract.type",
        "window_size": "keyword_extract.window_size",
        "hybrid_llm_weights": "keyword_extract.hybrid_llm_weights",
        "openai_chat_api_base": "openai.chat.api_base",
        "openai_chat_api_key": "openai.chat.api_key",
        "openai_chat_language_model": "openai.chat.language_model",
        "openai_extract_api_base": "openai.extract.api_base",
        "openai_extract_api_key": "openai.extract.api_key",
        "openai_extract_language_model": "openai.extract.language_model",
        "openai_text2gql_api_base": "openai.text2gql.api_base",
        "openai_text2gql_api_key": "openai.text2gql.api_key",
        "openai_text2gql_language_model": "openai.text2gql.language_model",
        "openai_embedding_api_base": "openai.embedding.api_base",
        "openai_embedding_api_key": "openai.embedding.api_key",
        "openai_embedding_model": "openai.embedding.model",
        "openai_chat_tokens": "openai.chat.tokens",
        "openai_extract_tokens": "openai.extract.tokens",
        "openai_text2gql_tokens": "openai.text2gql.tokens",
        "cohere_base_url": "cohere.base_url",
        "reranker_api_key": "reranker.api_key",
        "reranker_model": "reranker.model",
        "ollama_chat_host": "ollama.chat.host",
        "ollama_chat_port": "ollama.chat.port",
        "ollama_chat_language_model": "ollama.chat.language_model",
        "ollama_extract_host": "ollama.extract.host",
        "ollama_extract_port": "ollama.extract.port",
        "ollama_extract_language_model": "ollama.extract.language_model",
        "ollama_text2gql_host": "ollama.text2gql.host",
        "ollama_text2gql_port": "ollama.text2gql.port",
        "ollama_text2gql_language_model": "ollama.text2gql.language_model",
        "ollama_embedding_host": "ollama.embedding.host",
        "ollama_embedding_port": "ollama.embedding.port",
        "ollama_embedding_model": "ollama.embedding.model",
        "litellm_chat_api_key": "litellm.chat.api_key",
        "litellm_chat_api_base": "litellm.chat.api_base",
        "litellm_chat_language_model": "litellm.chat.language_model",
        "litellm_chat_tokens": "litellm.chat.tokens",
        "litellm_extract_api_key": "litellm.extract.api_key",
        "litellm_extract_api_base": "litellm.extract.api_base",
        "litellm_extract_language_model": "litellm.extract.language_model",
        "litellm_extract_tokens": "litellm.extract.tokens",
        "litellm_text2gql_api_key": "litellm.text2gql.api_key",
        "litellm_text2gql_api_base": "litellm.text2gql.api_base",
        "litellm_text2gql_language_model": "litellm.text2gql.language_model",
        "litellm_text2gql_tokens": "litellm.text2gql.tokens",
        "litellm_embedding_api_key": "litellm.embedding.api_key",
        "litellm_embedding_api_base": "litellm.embedding.api_base",
        "litellm_embedding_model": "litellm.embedding.model",
    }
    _env_var_map: ClassVar[dict[str, list[str]]] = {
        "language": ["LANGUAGE"],
        "chat_llm_type": ["CHAT_LLM_TYPE"],
        "extract_llm_type": ["EXTRACT_LLM_TYPE"],
        "text2gql_llm_type": ["TEXT2GQL_LLM_TYPE"],
        "embedding_type": ["EMBEDDING_TYPE"],
        "reranker_type": ["RERANKER_TYPE"],
        "keyword_extract_type": ["KEYWORD_EXTRACT_TYPE"],
        "window_size": ["WINDOW_SIZE"],
        "hybrid_llm_weights": ["HYBRID_LLM_WEIGHTS"],
        "openai_chat_api_base": ["OPENAI_CHAT_API_BASE", "OPENAI_BASE_URL"],
        "openai_chat_api_key": ["OPENAI_CHAT_API_KEY", "OPENAI_API_KEY"],
        "openai_chat_language_model": ["OPENAI_CHAT_LANGUAGE_MODEL"],
        "openai_chat_tokens": ["OPENAI_CHAT_TOKENS"],
        "openai_extract_api_base": ["OPENAI_EXTRACT_API_BASE", "OPENAI_BASE_URL"],
        "openai_extract_api_key": ["OPENAI_EXTRACT_API_KEY", "OPENAI_API_KEY"],
        "openai_extract_language_model": ["OPENAI_EXTRACT_LANGUAGE_MODEL"],
        "openai_extract_tokens": ["OPENAI_EXTRACT_TOKENS"],
        "openai_text2gql_api_base": ["OPENAI_TEXT2GQL_API_BASE", "OPENAI_BASE_URL"],
        "openai_text2gql_api_key": ["OPENAI_TEXT2GQL_API_KEY", "OPENAI_API_KEY"],
        "openai_text2gql_language_model": ["OPENAI_TEXT2GQL_LANGUAGE_MODEL"],
        "openai_text2gql_tokens": ["OPENAI_TEXT2GQL_TOKENS"],
        "openai_embedding_api_base": ["OPENAI_EMBEDDING_API_BASE", "OPENAI_EMBEDDING_BASE_URL", "OPENAI_BASE_URL"],
        "openai_embedding_api_key": ["OPENAI_EMBEDDING_API_KEY", "OPENAI_API_KEY"],
        "openai_embedding_model": ["OPENAI_EMBEDDING_MODEL"],
        "cohere_base_url": ["CO_API_URL", "COHERE_BASE_URL"],
        "reranker_api_key": ["RERANKER_API_KEY", "COHERE_API_KEY", "SILICONFLOW_API_KEY"],
        "reranker_model": ["RERANKER_MODEL"],
        "ollama_chat_host": ["OLLAMA_CHAT_HOST", "OLLAMA_HOST"],
        "ollama_chat_port": ["OLLAMA_CHAT_PORT", "OLLAMA_PORT"],
        "ollama_chat_language_model": ["OLLAMA_CHAT_LANGUAGE_MODEL"],
        "ollama_extract_host": ["OLLAMA_EXTRACT_HOST", "OLLAMA_HOST"],
        "ollama_extract_port": ["OLLAMA_EXTRACT_PORT", "OLLAMA_PORT"],
        "ollama_extract_language_model": ["OLLAMA_EXTRACT_LANGUAGE_MODEL"],
        "ollama_text2gql_host": ["OLLAMA_TEXT2GQL_HOST", "OLLAMA_HOST"],
        "ollama_text2gql_port": ["OLLAMA_TEXT2GQL_PORT", "OLLAMA_PORT"],
        "ollama_text2gql_language_model": ["OLLAMA_TEXT2GQL_LANGUAGE_MODEL"],
        "ollama_embedding_host": ["OLLAMA_EMBEDDING_HOST", "OLLAMA_HOST"],
        "ollama_embedding_port": ["OLLAMA_EMBEDDING_PORT", "OLLAMA_PORT"],
        "ollama_embedding_model": ["OLLAMA_EMBEDDING_MODEL"],
        "litellm_chat_api_key": ["LITELLM_CHAT_API_KEY", "LITELLM_API_KEY"],
        "litellm_chat_api_base": ["LITELLM_CHAT_API_BASE", "LITELLM_BASE_URL"],
        "litellm_chat_language_model": ["LITELLM_CHAT_LANGUAGE_MODEL"],
        "litellm_chat_tokens": ["LITELLM_CHAT_TOKENS"],
        "litellm_extract_api_key": ["LITELLM_EXTRACT_API_KEY", "LITELLM_API_KEY"],
        "litellm_extract_api_base": ["LITELLM_EXTRACT_API_BASE", "LITELLM_BASE_URL"],
        "litellm_extract_language_model": ["LITELLM_EXTRACT_LANGUAGE_MODEL"],
        "litellm_extract_tokens": ["LITELLM_EXTRACT_TOKENS"],
        "litellm_text2gql_api_key": ["LITELLM_TEXT2GQL_API_KEY", "LITELLM_API_KEY"],
        "litellm_text2gql_api_base": ["LITELLM_TEXT2GQL_API_BASE", "LITELLM_BASE_URL"],
        "litellm_text2gql_language_model": ["LITELLM_TEXT2GQL_LANGUAGE_MODEL"],
        "litellm_text2gql_tokens": ["LITELLM_TEXT2GQL_TOKENS"],
        "litellm_embedding_api_key": ["LITELLM_EMBEDDING_API_KEY", "LITELLM_API_KEY"],
        "litellm_embedding_api_base": ["LITELLM_EMBEDDING_API_BASE", "LITELLM_BASE_URL"],
        "litellm_embedding_model": ["LITELLM_EMBEDDING_MODEL"],
    }
    _mutable_persisted_fields: ClassVar[set[str]] = {
        "language",
        "chat_llm_type",
        "extract_llm_type",
        "text2gql_llm_type",
        "embedding_type",
        "reranker_type",
        "keyword_extract_type",
        "window_size",
        "hybrid_llm_weights",
        "openai_chat_api_base",
        "openai_chat_language_model",
        "openai_extract_api_base",
        "openai_extract_language_model",
        "openai_text2gql_api_base",
        "openai_text2gql_language_model",
        "openai_embedding_api_base",
        "openai_embedding_model",
        "openai_chat_tokens",
        "openai_extract_tokens",
        "openai_text2gql_tokens",
        "cohere_base_url",
        "reranker_model",
        "ollama_chat_host",
        "ollama_chat_port",
        "ollama_chat_language_model",
        "ollama_extract_host",
        "ollama_extract_port",
        "ollama_extract_language_model",
        "ollama_text2gql_host",
        "ollama_text2gql_port",
        "ollama_text2gql_language_model",
        "ollama_embedding_host",
        "ollama_embedding_port",
        "ollama_embedding_model",
        "litellm_chat_api_base",
        "litellm_chat_language_model",
        "litellm_chat_tokens",
        "litellm_extract_api_base",
        "litellm_extract_language_model",
        "litellm_extract_tokens",
        "litellm_text2gql_api_base",
        "litellm_text2gql_language_model",
        "litellm_text2gql_tokens",
        "litellm_embedding_api_base",
        "litellm_embedding_model",
    }

    language: Literal["EN", "CN"] = "EN"
    chat_llm_type: Literal["openai", "litellm", "ollama/local"] = "openai"
    extract_llm_type: Literal["openai", "litellm", "ollama/local"] = "openai"
    text2gql_llm_type: Literal["openai", "litellm", "ollama/local"] = "openai"
    embedding_type: Optional[Literal["openai", "litellm", "ollama/local"]] = "openai"
    reranker_type: Optional[Literal["cohere", "siliconflow"]] = None
    keyword_extract_type: Literal["llm", "textrank", "hybrid"] = "llm"
    window_size: Optional[int] = 3
    hybrid_llm_weights: Optional[float] = 0.5
    # TODO: divide RAG part if necessary
    # 1. OpenAI settings
    openai_chat_api_base: Optional[str] = "https://api.openai.com/v1"
    openai_chat_api_key: Optional[str] = None
    openai_chat_language_model: Optional[str] = "gpt-4.1-mini"
    openai_extract_api_base: Optional[str] = "https://api.openai.com/v1"
    openai_extract_api_key: Optional[str] = None
    openai_extract_language_model: Optional[str] = "gpt-4.1-mini"
    openai_text2gql_api_base: Optional[str] = "https://api.openai.com/v1"
    openai_text2gql_api_key: Optional[str] = None
    openai_text2gql_language_model: Optional[str] = "gpt-4.1-mini"
    openai_embedding_api_base: Optional[str] = "https://api.openai.com/v1"
    openai_embedding_api_key: Optional[str] = None
    openai_embedding_model: Optional[str] = "text-embedding-3-small"
    openai_chat_tokens: int = 8192
    openai_extract_tokens: int = 256
    openai_text2gql_tokens: int = 4096
    # 2. Rerank settings
    cohere_base_url: Optional[str] = "https://api.cohere.com/v1/rerank"
    reranker_api_key: Optional[str] = None
    reranker_model: Optional[str] = None
    # 3. Ollama settings
    ollama_chat_host: Optional[str] = "127.0.0.1"
    ollama_chat_port: Optional[int] = 11434
    ollama_chat_language_model: Optional[str] = None
    ollama_extract_host: Optional[str] = "127.0.0.1"
    ollama_extract_port: Optional[int] = 11434
    ollama_extract_language_model: Optional[str] = None
    ollama_text2gql_host: Optional[str] = "127.0.0.1"
    ollama_text2gql_port: Optional[int] = 11434
    ollama_text2gql_language_model: Optional[str] = None
    ollama_embedding_host: Optional[str] = "127.0.0.1"
    ollama_embedding_port: Optional[int] = 11434
    ollama_embedding_model: Optional[str] = None
    # 4. LiteLLM settings
    litellm_chat_api_key: Optional[str] = None
    litellm_chat_api_base: Optional[str] = None
    litellm_chat_language_model: Optional[str] = "openai/gpt-4.1-mini"
    litellm_chat_tokens: int = 8192
    litellm_extract_api_key: Optional[str] = None
    litellm_extract_api_base: Optional[str] = None
    litellm_extract_language_model: Optional[str] = "openai/gpt-4.1-mini"
    litellm_extract_tokens: int = 256
    litellm_text2gql_api_key: Optional[str] = None
    litellm_text2gql_api_base: Optional[str] = None
    litellm_text2gql_language_model: Optional[str] = "openai/gpt-4.1-mini"
    litellm_text2gql_tokens: int = 4096
    litellm_embedding_api_key: Optional[str] = None
    litellm_embedding_api_base: Optional[str] = None
    litellm_embedding_model: Optional[str] = "openai/text-embedding-3-small"

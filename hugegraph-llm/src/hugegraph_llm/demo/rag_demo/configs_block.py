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

import json
from functools import partial
from typing import Any, Optional

import gradio as gr
import requests
from requests.auth import HTTPBasicAuth

from hugegraph_llm.config import huge_settings, index_settings, llm_settings
from hugegraph_llm.config.manager import get_config_manager
from hugegraph_llm.config.mapping import is_sensitive_path
from hugegraph_llm.models.embeddings.litellm import LiteLLMEmbedding
from hugegraph_llm.models.llms.litellm import LiteLLMClient
from hugegraph_llm.utils.log import log

current_llm = "chat"


def test_litellm_embedding(api_key, api_base, model_name) -> int:
    llm_client = LiteLLMEmbedding(
        api_key=api_key,
        api_base=api_base,
        model_name=model_name,
    )
    try:
        response = llm_client.get_text_embedding("test")
        assert len(response) > 0
    except Exception as e:
        raise gr.Error(f"Error in litellm embedding call: {e}") from e
    gr.Info("Test connection successful~")
    return 200


def test_litellm_chat(api_key, api_base, model_name, max_tokens: int) -> int:
    try:
        llm_client = LiteLLMClient(
            api_key=api_key,
            api_base=api_base,
            model_name=model_name,
            max_tokens=max_tokens,
        )
        response = llm_client.generate(messages=[{"role": "user", "content": "hi"}])
        assert len(response) > 0
    except Exception as e:
        raise gr.Error(f"Error in litellm chat call: {e}") from e
    gr.Info("Test connection successful~")
    return 200


def test_api_connection(url, method="GET", headers=None, params=None, body=None, auth=None, origin_call=None) -> int:
    # TODO: use fastapi.request / starlette instead?
    log.debug("Request URL: %s", url)
    try:
        if method.upper() == "GET":
            resp = requests.get(url, headers=headers, params=params, timeout=(1.0, 5.0), auth=auth)
        elif method.upper() == "POST":
            resp = requests.post(
                url,
                headers=headers,
                params=params,
                json=body,
                timeout=(1.0, 5.0),
                auth=auth,
            )
        else:
            raise ValueError("Unsupported HTTP method, please use GET/POST instead")
    except requests.exceptions.RequestException as e:
        msg = f"Connection failed: {e}"
        log.error(msg)
        if origin_call is None:
            raise gr.Error(msg)
        return -1  # Error code

    if 200 <= resp.status_code < 300:
        msg = "Test connection successful~"
        log.info(msg)
        gr.Info(msg)
    else:
        msg = f"Connection failed with status code: {resp.status_code}, error: {resp.text}"
        log.error(msg)
        # TODO: Only the message returned by rag can be processed, and the other return values can't be processed
        if origin_call is None:
            try:
                raise gr.Error(json.loads(resp.text).get("message", msg))
            except (json.decoder.JSONDecodeError, AttributeError) as e:
                raise gr.Error(resp.text) from e
    return resp.status_code


def _persist_config_updates(config_obj: Any, updates: dict[str, Any]) -> None:
    if not updates:
        return

    manager = get_config_manager()
    config_class = config_obj.__class__
    if config_class not in manager.section_by_class:
        manager.register_config_class(config_class)

    field_paths = manager.field_to_global_path[config_class]
    persisted_patch: dict[str, Any] = {}
    secret_values: dict[str, Any] = {}
    for field_name, value in updates.items():
        if field_name not in field_paths:
            raise ValueError(f"Unknown config field: {field_name}")

        setattr(config_obj, field_name, value)
        global_path = field_paths[field_name]
        if is_sensitive_path(global_path):
            env_names = manager.global_env_aliases.get(global_path, [])
            if env_names and value not in (None, ""):
                secret_values[env_names[0]] = value
        else:
            persisted_patch[field_name] = value

    if persisted_patch:
        config_obj.update_config(persisted_patch)
    if secret_values:
        manager.update_secret_env(secret_values)

    refreshed = manager.get_section_flat(config_class)
    for field_name, value in refreshed.items():
        setattr(config_obj, field_name, value)


def _has_openai_role_api_key(role: str) -> bool:
    value = getattr(llm_settings, f"openai_{role}_api_key", None)
    return bool(str(value).strip()) if value is not None else False


def apply_vector_engine(engine: str):
    try:
        _persist_config_updates(index_settings, {"cur_vector_index": engine})
    except Exception:  # pylint: disable=W0718
        pass
    gr.Info("Configured!")


def apply_vector_engine_backend(  # pylint: disable=too-many-branches
    engine: str,
    host: Optional[str] = None,
    port: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    api_key: Optional[str] = None,
    origin_call=None,
) -> int:
    """Test connection and persist per-engine connection settings"""
    status_code = -1

    # Test connection first
    try:
        if engine == "Milvus":
            from pymilvus import connections, utility

            connections.connect(host=host, port=int(port or 19530), user=user or "", password=password or "")
            # Test if we can list collections
            _ = utility.list_collections()
            connections.disconnect("default")
            status_code = 200
        elif engine == "Qdrant":
            from qdrant_client import QdrantClient

            client = QdrantClient(host=host, port=int(port or 6333), api_key=api_key)
            # Test if we can get collections
            _ = client.get_collections()
            status_code = 200
    except ImportError as e:
        msg = f"Missing dependency: {e}. Please install with: uv sync --extra vectordb"
        if origin_call is None:
            raise gr.Error(msg) from e
        return -1
    except Exception as e:  # pylint: disable=broad-exception-caught
        msg = f"Connection failed: {e}"
        log.error(msg)
        if origin_call is None:
            raise gr.Error(msg) from e
        return -1

    # Persist settings after successful test
    updates: dict[str, Any] = {"cur_vector_index": engine}
    if engine == "Milvus":
        if host is not None:
            updates["milvus_host"] = host
        if port is not None and str(port).strip():
            updates["milvus_port"] = int(port)
        updates["milvus_user"] = user or ""
        updates["milvus_password"] = password or ""
    elif engine == "Qdrant":
        if host is not None:
            updates["qdrant_host"] = host
        if port is not None and str(port).strip():
            updates["qdrant_port"] = int(port)
        updates["qdrant_api_key"] = api_key or None

    try:
        _persist_config_updates(index_settings, updates)
    except Exception:  # pylint: disable=W0718
        pass
    gr.Info("Configured!")
    return status_code


def apply_embedding_config(arg1, arg2, arg3, origin_call=None) -> int:
    status_code = -1
    embedding_option = llm_settings.embedding_type
    updates: dict[str, Any] = {"embedding_type": embedding_option}
    if embedding_option == "openai":
        updates.update(
            {
                "openai_embedding_api_key": arg1,
                "openai_embedding_api_base": arg2,
                "openai_embedding_model": arg3,
            }
        )
        test_url = arg2 + "/embeddings"
        headers = {"Authorization": f"Bearer {arg1}"}
        data = {"model": arg3, "input": "test"}
        status_code = test_api_connection(test_url, method="POST", headers=headers, body=data, origin_call=origin_call)
    elif embedding_option == "ollama/local":
        updates.update(
            {
                "ollama_embedding_host": arg1,
                "ollama_embedding_port": int(arg2),
                "ollama_embedding_model": arg3,
            }
        )
        status_code = test_api_connection(f"http://{arg1}:{arg2}", origin_call=origin_call)
    elif embedding_option == "litellm":
        updates.update(
            {
                "litellm_embedding_api_key": arg1,
                "litellm_embedding_api_base": arg2,
                "litellm_embedding_model": arg3,
            }
        )
        status_code = test_litellm_embedding(arg1, arg2, arg3)
    _persist_config_updates(llm_settings, updates)
    gr.Info("Configured!")
    return status_code


def apply_reranker_config(
    reranker_api_key: Optional[str] = None,
    reranker_model: Optional[str] = None,
    cohere_base_url: Optional[str] = None,
    origin_call=None,
) -> int:
    status_code = -1
    reranker_option = llm_settings.reranker_type
    updates: dict[str, Any] = {"reranker_type": reranker_option}
    if reranker_option == "cohere":
        updates.update(
            {
                "reranker_api_key": reranker_api_key,
                "reranker_model": reranker_model,
                "cohere_base_url": cohere_base_url,
            }
        )
        headers = {"Authorization": f"Bearer {reranker_api_key}"}
        status_code = test_api_connection(
            cohere_base_url.rsplit("/", 1)[0] + "/check-api-key",
            method="POST",
            headers=headers,
            origin_call=origin_call,
        )
    elif reranker_option == "siliconflow":
        updates.update(
            {
                "reranker_api_key": reranker_api_key,
                "reranker_model": reranker_model,
            }
        )
        from pyhugegraph.utils.constants import Constants

        headers = {
            "accept": Constants.HEADER_CONTENT_TYPE,
            "authorization": f"Bearer {reranker_api_key}",
        }
        status_code = test_api_connection(
            "https://api.siliconflow.cn/v1/user/info",
            headers=headers,
            origin_call=origin_call,
        )
    _persist_config_updates(llm_settings, updates)
    gr.Info("Configured!")
    return status_code


def apply_graph_config(url, name, user, pwd, gs, origin_call=None) -> int:
    # Add URL prefix automatically to improve the user experience
    if url and not (url.startswith("http://") or url.startswith("https://")):
        url = f"http://{url}"

    # Test graph connection (Auth)
    if gs and gs.strip():
        test_url = f"{url}/graphspaces/{gs}/graphs/{name}/schema"
    else:
        test_url = f"{url}/graphs/{name}/schema"
    auth = HTTPBasicAuth(user, pwd)
    # for http api return status
    response = test_api_connection(test_url, auth=auth, origin_call=origin_call)
    _persist_config_updates(
        huge_settings,
        {
            "graph_url": url,
            "graph_name": name,
            "graph_user": user,
            "graph_pwd": pwd,
            "graph_space": gs,
        },
    )
    return response


def apply_llm_config(
    current_llm_config,
    api_key_or_host,
    api_base_or_port,
    model_name,
    max_tokens,
    origin_call=None,
) -> int:
    log.debug("current llm in apply_llm_config is %s", current_llm_config)
    llm_option = getattr(llm_settings, f"{current_llm_config}_llm_type")
    log.debug("llm option in apply_llm_config is %s", llm_option)
    status_code = -1
    updates: dict[str, Any] = {f"{current_llm_config}_llm_type": llm_option}

    if llm_option == "openai":
        updates.update(
            {
                f"openai_{current_llm_config}_api_key": api_key_or_host,
                f"openai_{current_llm_config}_api_base": api_base_or_port,
                f"openai_{current_llm_config}_language_model": model_name,
                f"openai_{current_llm_config}_tokens": int(max_tokens),
            }
        )
        test_url = api_base_or_port + "/chat/completions"
        data = {
            "model": model_name,
            "temperature": 0.01,
            "messages": [{"role": "user", "content": "test"}],
        }
        headers = {"Authorization": f"Bearer {api_key_or_host}"}
        status_code = test_api_connection(test_url, method="POST", headers=headers, body=data, origin_call=origin_call)

    elif llm_option == "ollama/local":
        updates.update(
            {
                f"ollama_{current_llm_config}_host": api_key_or_host,
                f"ollama_{current_llm_config}_port": int(api_base_or_port),
                f"ollama_{current_llm_config}_language_model": model_name,
            }
        )
        status_code = test_api_connection(f"http://{api_key_or_host}:{api_base_or_port}", origin_call=origin_call)

    elif llm_option == "litellm":
        updates.update(
            {
                f"litellm_{current_llm_config}_api_key": api_key_or_host,
                f"litellm_{current_llm_config}_api_base": api_base_or_port,
                f"litellm_{current_llm_config}_language_model": model_name,
                f"litellm_{current_llm_config}_tokens": int(max_tokens),
            }
        )
        status_code = test_litellm_chat(api_key_or_host, api_base_or_port, model_name, int(max_tokens))

    gr.Info("Configured!")
    _persist_config_updates(llm_settings, updates)
    return status_code


# TODO: refactor the function to reduce the number of statements & separate the logic
# pylint: disable=C0301,E1101
def create_configs_block() -> list:
    # pylint: disable=R0915 (too-many-statements)
    with gr.Accordion("1. Set up the HugeGraph server.", open=False):
        with gr.Row():
            graph_config_input = [
                gr.Textbox(
                    value=huge_settings.graph_url,
                    label="url",
                    info="IP:PORT (e.g. 127.0.0.1:8080) or full URL (e.g. http://127.0.0.1:8080)",
                ),
                gr.Textbox(
                    value=huge_settings.graph_name,
                    label="graph",
                    info="The graph name of HugeGraph-Server instance",
                ),
                gr.Textbox(
                    value=huge_settings.graph_user,
                    label="user",
                    info="Username for graph server auth",
                ),
                gr.Textbox(
                    value=huge_settings.graph_pwd,
                    label="pwd",
                    type="password",
                    info="Password for graph server auth",
                ),
                gr.Textbox(
                    value=huge_settings.graph_space,
                    label="graphspace (Optional)",
                    info="Namespace for multi-tenant scenarios (leave empty if not using graphspaces)",
                ),
            ]
        graph_config_button = gr.Button("Apply Configuration")
    graph_config_button.click(apply_graph_config, inputs=graph_config_input)  # pylint: disable=no-member

    # TODO : use OOP to refactor the following code
    with gr.Accordion("2. Set up the LLM.", open=False):
        gr.Markdown(
            "> Tips: The OpenAI option also support openai style api from other providers. "
            "**Refresh the page** to load the **latest configs** in __UI__."
        )
        with gr.Tab(label="chat"):
            chat_llm_dropdown = gr.Dropdown(
                choices=["openai", "litellm", "ollama/local"],
                value=getattr(llm_settings, "chat_llm_type"),
                label="type",
            )
            apply_llm_config_with_chat_op = partial(apply_llm_config, "chat")

            @gr.render(inputs=[chat_llm_dropdown])
            def chat_llm_settings(llm_type):
                llm_settings.chat_llm_type = llm_type
                if llm_type == "openai":
                    llm_config_input = [
                        gr.Textbox(
                            value=getattr(llm_settings, "openai_chat_api_key"),
                            label="api_key",
                            type="password",
                        ),
                        gr.Textbox(
                            value=getattr(llm_settings, "openai_chat_api_base"),
                            label="api_base",
                        ),
                        gr.Textbox(
                            value=getattr(llm_settings, "openai_chat_language_model"),
                            label="model_name",
                        ),
                        gr.Textbox(
                            value=getattr(llm_settings, "openai_chat_tokens"),
                            label="max_token",
                        ),
                    ]
                elif llm_type == "ollama/local":
                    llm_config_input = [
                        gr.Textbox(
                            value=getattr(llm_settings, "ollama_chat_host"),
                            label="host",
                        ),
                        gr.Textbox(
                            value=str(getattr(llm_settings, "ollama_chat_port")),
                            label="port",
                        ),
                        gr.Textbox(
                            value=getattr(llm_settings, "ollama_chat_language_model"),
                            label="model_name",
                        ),
                        gr.Textbox(value="", visible=False),
                    ]
                elif llm_type == "litellm":
                    llm_config_input = [
                        gr.Textbox(
                            value=getattr(llm_settings, "litellm_chat_api_key"),
                            label="api_key",
                            type="password",
                        ),
                        gr.Textbox(
                            value=getattr(llm_settings, "litellm_chat_api_base"),
                            label="api_base",
                            info="If you want to use the default api_base, please keep it blank",
                        ),
                        gr.Textbox(
                            value=getattr(llm_settings, "litellm_chat_language_model"),
                            label="model_name",
                            info="Please refer to https://docs.litellm.ai/docs/providers",
                        ),
                        gr.Textbox(
                            value=getattr(llm_settings, "litellm_chat_tokens"),
                            label="max_token",
                        ),
                    ]
                else:
                    llm_config_input = [gr.Textbox(value="", visible=False) for _ in range(4)]
                llm_config_button = gr.Button("Apply configuration")
                llm_config_button.click(apply_llm_config_with_chat_op, inputs=llm_config_input)
                if not _has_openai_role_api_key("text2gql"):
                    llm_config_button.click(apply_llm_config_with_text2gql_op, inputs=llm_config_input)
                if not _has_openai_role_api_key("extract"):
                    llm_config_button.click(apply_llm_config_with_extract_op, inputs=llm_config_input)

        with gr.Tab(label="mini_tasks"):
            extract_llm_dropdown = gr.Dropdown(
                choices=["openai", "litellm", "ollama/local"],
                value=getattr(llm_settings, "extract_llm_type"),
                label="type",
            )
            apply_llm_config_with_extract_op = partial(apply_llm_config, "extract")

            @gr.render(inputs=[extract_llm_dropdown])
            def extract_llm_settings(llm_type):
                llm_settings.extract_llm_type = llm_type
                if llm_type == "openai":
                    llm_config_input = [
                        gr.Textbox(
                            value=getattr(llm_settings, "openai_extract_api_key"),
                            label="api_key",
                            type="password",
                        ),
                        gr.Textbox(
                            value=getattr(llm_settings, "openai_extract_api_base"),
                            label="api_base",
                        ),
                        gr.Textbox(
                            value=getattr(llm_settings, "openai_extract_language_model"),
                            label="model_name",
                        ),
                        gr.Textbox(
                            value=getattr(llm_settings, "openai_extract_tokens"),
                            label="max_token",
                        ),
                    ]
                elif llm_type == "ollama/local":
                    llm_config_input = [
                        gr.Textbox(
                            value=getattr(llm_settings, "ollama_extract_host"),
                            label="host",
                        ),
                        gr.Textbox(
                            value=str(getattr(llm_settings, "ollama_extract_port")),
                            label="port",
                        ),
                        gr.Textbox(
                            value=getattr(llm_settings, "ollama_extract_language_model"),
                            label="model_name",
                        ),
                        gr.Textbox(value="", visible=False),
                    ]
                elif llm_type == "litellm":
                    llm_config_input = [
                        gr.Textbox(
                            value=getattr(llm_settings, "litellm_extract_api_key"),
                            label="api_key",
                            type="password",
                        ),
                        gr.Textbox(
                            value=getattr(llm_settings, "litellm_extract_api_base"),
                            label="api_base",
                            info="If you want to use the default api_base, please keep it blank",
                        ),
                        gr.Textbox(
                            value=getattr(llm_settings, "litellm_extract_language_model"),
                            label="model_name",
                            info="Please refer to https://docs.litellm.ai/docs/providers",
                        ),
                        gr.Textbox(
                            value=getattr(llm_settings, "litellm_extract_tokens"),
                            label="max_token",
                        ),
                    ]
                else:
                    llm_config_input = [gr.Textbox(value="", visible=False) for _ in range(4)]
                llm_config_button = gr.Button("Apply configuration")
                llm_config_button.click(apply_llm_config_with_extract_op, inputs=llm_config_input)

        with gr.Tab(label="text2gql"):
            text2gql_llm_dropdown = gr.Dropdown(
                choices=["openai", "litellm", "ollama/local"],
                value=getattr(llm_settings, "text2gql_llm_type"),
                label="type",
            )
            apply_llm_config_with_text2gql_op = partial(apply_llm_config, "text2gql")

            @gr.render(inputs=[text2gql_llm_dropdown])
            def text2gql_llm_settings(llm_type):
                llm_settings.text2gql_llm_type = llm_type
                if llm_type == "openai":
                    llm_config_input = [
                        gr.Textbox(
                            value=getattr(llm_settings, "openai_text2gql_api_key"),
                            label="api_key",
                            type="password",
                        ),
                        gr.Textbox(
                            value=getattr(llm_settings, "openai_text2gql_api_base"),
                            label="api_base",
                        ),
                        gr.Textbox(
                            value=getattr(llm_settings, "openai_text2gql_language_model"),
                            label="model_name",
                        ),
                        gr.Textbox(
                            value=getattr(llm_settings, "openai_text2gql_tokens"),
                            label="max_token",
                        ),
                    ]
                elif llm_type == "ollama/local":
                    llm_config_input = [
                        gr.Textbox(
                            value=getattr(llm_settings, "ollama_text2gql_host"),
                            label="host",
                        ),
                        gr.Textbox(
                            value=str(getattr(llm_settings, "ollama_text2gql_port")),
                            label="port",
                        ),
                        gr.Textbox(
                            value=getattr(llm_settings, "ollama_text2gql_language_model"),
                            label="model_name",
                        ),
                        gr.Textbox(value="", visible=False),
                    ]
                elif llm_type == "litellm":
                    llm_config_input = [
                        gr.Textbox(
                            value=getattr(llm_settings, "litellm_text2gql_api_key"),
                            label="api_key",
                            type="password",
                        ),
                        gr.Textbox(
                            value=getattr(llm_settings, "litellm_text2gql_api_base"),
                            label="api_base",
                            info="If you want to use the default api_base, please keep it blank",
                        ),
                        gr.Textbox(
                            value=getattr(llm_settings, "litellm_text2gql_language_model"),
                            label="model_name",
                            info="Please refer to https://docs.litellm.ai/docs/providers",
                        ),
                        gr.Textbox(
                            value=getattr(llm_settings, "litellm_text2gql_tokens"),
                            label="max_token",
                        ),
                    ]
                else:
                    llm_config_input = [gr.Textbox(value="", visible=False) for _ in range(4)]
                llm_config_button = gr.Button("Apply configuration")
                llm_config_button.click(apply_llm_config_with_text2gql_op, inputs=llm_config_input)

    with gr.Accordion("3. Set up the Embedding.", open=False):
        embedding_dropdown = gr.Dropdown(
            choices=["openai", "litellm", "ollama/local"],
            value=llm_settings.embedding_type,
            label="Embedding",
        )

        @gr.render(inputs=[embedding_dropdown])
        def embedding_settings(embedding_type):
            llm_settings.embedding_type = embedding_type
            if embedding_type == "openai":
                with gr.Row():
                    embedding_config_input = [
                        gr.Textbox(
                            value=llm_settings.openai_embedding_api_key,
                            label="api_key",
                            type="password",
                        ),
                        gr.Textbox(
                            value=llm_settings.openai_embedding_api_base,
                            label="api_base",
                        ),
                        gr.Textbox(
                            value=llm_settings.openai_embedding_model,
                            label="model_name",
                        ),
                    ]
            elif embedding_type == "ollama/local":
                with gr.Row():
                    embedding_config_input = [
                        gr.Textbox(value=llm_settings.ollama_embedding_host, label="host"),
                        gr.Textbox(value=str(llm_settings.ollama_embedding_port), label="port"),
                        gr.Textbox(
                            value=llm_settings.ollama_embedding_model,
                            label="model_name",
                        ),
                    ]
            elif embedding_type == "litellm":
                with gr.Row():
                    embedding_config_input = [
                        gr.Textbox(
                            value=getattr(llm_settings, "litellm_embedding_api_key"),
                            label="api_key",
                            type="password",
                        ),
                        gr.Textbox(
                            value=getattr(llm_settings, "litellm_embedding_api_base"),
                            label="api_base",
                            info="If you want to use the default api_base, please keep it blank",
                        ),
                        gr.Textbox(
                            value=getattr(llm_settings, "litellm_embedding_model"),
                            label="model_name",
                            info="Please refer to https://docs.litellm.ai/docs/embedding/supported_embedding",
                        ),
                    ]
            else:
                embedding_config_input = [
                    gr.Textbox(value="", visible=False),
                    gr.Textbox(value="", visible=False),
                    gr.Textbox(value="", visible=False),
                ]

            embedding_config_button = gr.Button("Apply Configuration")

            # Call the separate apply_embedding_configuration function here
            embedding_config_button.click(  # pylint: disable=no-member
                fn=apply_embedding_config,
                inputs=embedding_config_input,  # pylint: disable=no-member
            )

    with gr.Accordion("4. Set up the Reranker.", open=False):
        reranker_dropdown = gr.Dropdown(
            choices=["cohere", "siliconflow", ("default/offline", "None")],
            value=llm_settings.reranker_type or "None",
            label="Reranker",
        )

        @gr.render(inputs=[reranker_dropdown])
        def reranker_settings(reranker_type):
            llm_settings.reranker_type = reranker_type if reranker_type != "None" else None
            if reranker_type == "cohere":
                with gr.Row():
                    reranker_config_input = [
                        gr.Textbox(
                            value=llm_settings.reranker_api_key,
                            label="api_key",
                            type="password",
                        ),
                        gr.Textbox(value=llm_settings.reranker_model, label="model"),
                        gr.Textbox(value=llm_settings.cohere_base_url, label="base_url"),
                    ]
            elif reranker_type == "siliconflow":
                with gr.Row():
                    reranker_config_input = [
                        gr.Textbox(
                            value=llm_settings.reranker_api_key,
                            label="api_key",
                            type="password",
                        ),
                        gr.Textbox(
                            value="BAAI/bge-reranker-v2-m3",
                            label="model",
                            info="Please refer to https://siliconflow.cn/pricing",
                        ),
                        gr.Textbox(value="", visible=False),
                    ]
            else:
                reranker_config_input = [
                    gr.Textbox(value="", visible=False),
                    gr.Textbox(value="", visible=False),
                    gr.Textbox(value="", visible=False),
                ]
            reranker_config_button = gr.Button("Apply configuration")

            # TODO: use "gr.update()" or other way to update the config in time (refactor the click event)
            # Call the separate apply_reranker_configuration function here
            reranker_config_button.click(  # pylint: disable=no-member
                fn=apply_reranker_config,
                inputs=reranker_config_input,  # pylint: disable=no-member
            )

    with gr.Accordion("5. Set up the vector engine.", open=False):
        engine_selector = gr.Dropdown(
            choices=["Faiss", "Milvus", "Qdrant"],
            value=index_settings.cur_vector_index,
            label="Select vector engine.",
        )
        engine_selector.select(
            fn=lambda engine: setattr(index_settings, "cur_vector_index", engine),
            inputs=[engine_selector],
        )

        @gr.render(inputs=[engine_selector])
        def vector_engine_settings(engine):
            if engine == "Milvus":
                with gr.Row():
                    milvus_inputs = [
                        gr.Textbox(value=index_settings.milvus_host, label="host"),
                        gr.Textbox(value=str(index_settings.milvus_port), label="port"),
                        gr.Textbox(value=index_settings.milvus_user, label="user"),
                        gr.Textbox(value=index_settings.milvus_password, label="password", type="password"),
                    ]
                apply_backend_button = gr.Button("Apply Configuration")
                apply_backend_button.click(partial(apply_vector_engine_backend, "Milvus"), inputs=milvus_inputs)
            elif engine == "Qdrant":
                with gr.Row():
                    qdrant_inputs = [
                        gr.Textbox(value=index_settings.qdrant_host, label="host"),
                        gr.Textbox(value=str(index_settings.qdrant_port), label="port"),
                        gr.Textbox(
                            value=(index_settings.qdrant_api_key or ""),
                            label="api_key",
                            type="password",
                        ),
                    ]
                apply_backend_button = gr.Button("Apply Configuration")
                apply_backend_button.click(
                    lambda h, p, k: apply_vector_engine_backend("Qdrant", h, p, None, None, k),
                    inputs=qdrant_inputs,
                )
            else:
                gr.Markdown("✅ Faiss 本地索引无需额外配置。")
                apply_faiss_button = gr.Button("Apply Configuration")
                apply_faiss_button.click(lambda: apply_vector_engine(engine))

    # The reason for returning this partial value is the functional need to refresh the ui
    return graph_config_input


def get_header_with_language_indicator(language: str) -> str:
    language_class = language.lower()

    if language == "CN":
        title_text = "当前prompt语言: 中文 (CN)"
    else:
        title_text = "Current prompt Language: English (EN)"
    html_content = f"""
    <div class="header-container">
        <h1 class="header-title">HugeGraph RAG Platform 🚀</h1>
        <div class="language-indicator-container">
            <div class="language-indicator {language_class}">
                {language}
            </div>
            <div class="custom-tooltip">
                {title_text}
            </div>
        </div>
    </div>
    """
    return html_content

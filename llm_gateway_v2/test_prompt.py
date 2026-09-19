import httpx


response = httpx.post(
    "http://127.0.0.1:8001/v1/llm",
    headers={"Authorization": "Bearer test-key"},
    json={
        "model": "general-primary",
        "messages": [
            {"role": "user", "content": "差旅报销需要哪些材料？"},
        ],
        "prompt": {
            "name": "knowledge_decision",
            "version": "v1",
            "variables": {"product_name": "差旅助手"},
        },
    },
    timeout=60.0,
)

print(f"状态码: {response.status_code}")
print(f"响应 JSON: {response.json()}")

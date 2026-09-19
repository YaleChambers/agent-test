import httpx


def main():
    url = "http://127.0.0.1:8001/v1/llm"
    payload = {
        "model": "general-primary",
        "messages": [
            {"role": "user", "content": "提取：Ada，36岁"},
        ],
        "response_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
            "required": ["name", "age"],
            "additionalProperties": False,
        },
    }

    print("发送请求...")
    response = httpx.post(
        url,
        headers={"Authorization": "Bearer test-key"},
        json=payload,
        timeout=60,
    )
    print(f"状态码: {response.status_code}")
    print(f"响应: {response.json()}")


if __name__ == "__main__":
    main()
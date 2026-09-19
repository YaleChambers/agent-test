import httpx


url = "http://localhost:8000/v1/llm/stream"
payload = {
    "model": "general-primary",
    "messages": [{"role": "user", "content": "用三句话解释什么是 Python"}],
}

try:
    with httpx.stream("POST", url, json=payload, timeout=60.0) as response:
        response.raise_for_status()
        for line_number, line in enumerate(response.iter_lines(), start=1):
            if line:
                print(f"{line_number}: {line}", flush=True)
except Exception as exc:
    print(f"请求失败: {exc}", flush=True)

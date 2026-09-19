import httpx


url = "http://127.0.0.1:8001/v1/llm/stream"
payload = {
    "model": "general-primary",
    "messages": [{"role": "user", "content": "用 5000 字详细讲一下 Python 的历史"}],
}
headers = {"Authorization": "Bearer test-key"}

with httpx.stream("POST", url, headers=headers, json=payload, timeout=60.0) as response:
    response.raise_for_status()
    line_count = 0
    for line in response.iter_lines():
        if not line:
            continue
        print(line, flush=True)
        line_count += 1
        if line_count >= 3:
            print("准备断开...", flush=True)
            response.close()
            break

print("客户端已断开")

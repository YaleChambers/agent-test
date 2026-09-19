import httpx


response = httpx.post(
	"http://127.0.0.1:8000/v1/llm",
	json={
		"model": "general-primary",
		"messages": [{"role": "user", "content": "你好"}],
	},
	timeout=60.0,
)

print(response.status_code)
print(response.text)

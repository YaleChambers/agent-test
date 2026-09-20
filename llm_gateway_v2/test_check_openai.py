# 先启动服务：uvicorn app.main:app --reload --port 8001
# 再执行：python test_check_openai.py
# 跑完可删除

from openai import OpenAI


client = OpenAI(
    base_url="http://localhost:8001/v1",
    api_key="dummy",
    default_headers={"Authorization": "Bearer test-key"},
)


resp = client.chat.completions.create(
    model="general-primary",
    messages=[{"role": "user", "content": "用一句话介绍你自己"}],
)
print("model:", resp.model)
print("content:", resp.choices[0].message.content)
print("usage:", resp.usage)


try:
    client.chat.completions.create(
        model="general-primary",
        messages=[{"role": "user", "content": "hi"}],
        stream=True,
    )
    print("ERROR: 应该报错但没报")
except Exception as e:
    print("got expected error:", type(e).__name__, str(e)[:200])

import os
from zhipuai import ZhipuAI

API_KEY = "5720f5ac3a1d456fbf98191dba62d18e.rDpN75gxaQCoF7PN"
client = ZhipuAI(api_key=API_KEY)

def ask_lingshan_bot(messages):
    """
    🌟 最终版：方案二绝对同步大脑
    【核心优化】：关闭流式(stream=False)，同时将温度(temperature=0.0)降到最低，
    确保相同问题吐出绝对相同的文本，100%命中本地语音缓存池。
    """
    system_prompt = {
        "role": "system", 
        "content": "你是一个高效、生动、专业的无锡灵山胜境和拈花湾 AI 导游专家。请直接回答游客的问题，内容要点清晰，字数必须严格控制在 150 字以内！"
    }
    
    history_messages = [msg for msg in messages if msg["role"] != "system"]
    recent_history = history_messages[-6:] 
    formatted_messages = [system_prompt] + recent_history

    try:
        response = client.chat.completions.create(
            model="glm-4-flash",
            messages=formatted_messages,
            stream=False,      # 关闭流式
            temperature=0.0    # 🌟 锁死回答，消除随机性
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"🎒 哎呀，导游的思路稍微断了一下。错误快报：{e}"
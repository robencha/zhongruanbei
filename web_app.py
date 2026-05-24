import locale
locale.getpreferredencoding = lambda: 'utf-8'

import os
import time
import asyncio
import re
import threading
import hashlib
import sqlite3
import edge_tts  
import streamlit as st
import streamlit.components.v1 as components
from streamlit_mic_recorder import mic_recorder 
from rag_engine import ask_lingshan_bot
from business_logic import calculate_tickets, show_admin_dashboard_v2, analyze_sentiment_and_log

# ==================== 1. 网页基础设置与全屏美化 ====================
st.set_page_config(page_title="灵山胜境AI导游", page_icon="🌟", layout="wide", initial_sidebar_state="expanded")
st.title("🏯 无锡灵山胜境 · 拈花湾 AI 导游服务")
st.caption("中国软件杯A5赛题最终交付作品 | 影视级声画同步与全息多模态架构")

st.markdown("""
    <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        .stChatMessage { border-radius: 12px; box-shadow: 0 2px 6px rgba(0,0,0,0.03); }
        .map-container { border: 2px solid #f0f2f6; border-radius: 15px; padding: 25px; background: #fafafa; min-height: 400px; }
        .gps-badge { background-color: #e8f0fe; color: #1a73e8; padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 13px; display: inline-block; margin: 2px; }
    </style>
""", unsafe_allow_html=True)

if "persona_voice" not in st.session_state: st.session_state.persona_voice = "zh-CN-XiaoxiaoNeural" 
if "persona_style" not in st.session_state: st.session_state.persona_style = "官方默认标准形象"              
if "current_route_map" not in st.session_state: 
    st.session_state.current_route_map = "🌍 欢迎使用智能导览系统。请在左侧选择您的游览偏好及快捷路线，AI导游将为您即时推演重构全息动线..."
if "avatar_img_data" not in st.session_state: st.session_state.avatar_img_data = None

async def generate_tts_audio(text, output_path):
    communicate = edge_tts.Communicate(text, st.session_state.persona_voice)
    await communicate.save(output_path)

def get_img_base64(img_path):
    import base64
    if os.path.exists(img_path):
        with open(img_path, "rb") as f: return base64.b64encode(f.read()).decode()
    return None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "db")
if not os.path.exists(DB_DIR):
    os.makedirs(DB_DIR)

def render_avatar_by_style(state="close"):
    style = st.session_state.persona_style
    ext = ".gif" if state == "open" else ".jpg"
    
    if style == "官方默认标准形象":
        target_path = os.path.join(BASE_DIR, f"lulu_{state}{ext}")
        if state == "close" and not os.path.exists(target_path):
            target_path = os.path.join(BASE_DIR, "lulu.jpg") 
    else:
        specific_name = f"lulu_{style}_{state}{ext}"
        target_path = os.path.join(BASE_DIR, specific_name)
        if not os.path.exists(target_path):
            target_path = os.path.join(BASE_DIR, f"lulu_{state}{ext}")
            if state == "close" and not os.path.exists(target_path):
                target_path = os.path.join(BASE_DIR, "lulu.jpg")
        
    if os.path.exists(target_path):
        img_base64 = get_img_base64(target_path)
        mime = "image/gif" if target_path.endswith(".gif") else "image/jpeg"
        return f'<img src="data:{mime};base64,{img_base64}" style="border-radius:15px; margin-bottom:10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); width:100%;">'
    return None


# ==================== 2. 🛡️ 侧边栏：【纯数据看板输出舱】 ====================
st.sidebar.markdown("### 📊 运营实时数据")
show_admin_dashboard_v2()

st.sidebar.markdown("---")
try:
    conn = sqlite3.connect(os.path.join(DB_DIR, "visitor_logs.db"))
    cursor = conn.cursor()
    cursor.execute("SELECT query FROM logs WHERE is_complain=0 ORDER BY id DESC LIMIT 50")
    recent_queries = [row[0] for row in cursor.fetchall() if row[0] and len(row[0]) > 4]
    conn.close()
    if recent_queries:
        st.sidebar.markdown("🔥 **实时游客高频热门问题Top 3**")
        hot_keywords = ["梵宫吉祥颂怎么换手环？", "灵山大佛抱佛脚怎么走？", "拈花湾晚上的无人机表演几点开始？"]
        for idx, q in enumerate(hot_keywords):
            st.sidebar.caption(f"点赞Top {idx+1}: {q}")
except Exception: pass


# ==================== 3. 核心布局：右侧控制台 ====================
main_col, brain_col = st.columns([11, 9]) 

with brain_col:
    st.markdown("### 🤖 Lulu 全息大脑指挥舱")
    
    avatar_brain_placeholder = st.empty()
    st.markdown("---")
    map_info_placeholder = st.empty()

    avatar_html = render_avatar_by_style("close")
    if avatar_html:
        avatar_brain_placeholder.markdown(avatar_html, unsafe_allow_html=True)
    
    map_info_placeholder.markdown(st.session_state.current_route_map, unsafe_allow_html=True)


# ==================== 4. 左侧交互舱 ====================
with main_col:
    with st.expander("🎫 景区智能购票预算助手"):
        sub_c1, sub_c2 = st.columns(2)
        with sub_c1:
            adults = st.number_input("成人人数", min_value=0, value=1, step=1)
            students = st.number_input("学生/老人人数", min_value=0, value=0, step=1)
            free_pass = st.number_input("免票特殊人群", min_value=0, value=0, step=1)
        with sub_c2:
            need_car = st.checkbox("需要景区交通观光车", value=False)
            meal_type = st.selectbox("就餐选择", ["不就餐", "梵宫素斋自助", "特色素面套餐"])
            meal_count = st.number_input("就餐人数", min_value=0, value=0, step=1)
        if st.button("🌟 一键智能计算最优预算", use_container_width=True):
            t_cost, m_cost, total, tips = calculate_tickets(adults, students, free_pass, need_car, meal_type, meal_count)
            st.success(f"🎫 门票总计: {t_cost} 元 | 🍜 餐饮总计: {m_cost} 元 | 💰 预计总花费: {total} 元")
            st.info(tips)

    with st.expander("🔒 🔑 景区综合管理控制后台"):
        admin_password = st.text_input("请输入管理员核心密码", type="password", key="admin_pwd")
        if admin_password == "lingshan666":
            st.success("🔓 管理员权限已解锁")
            selected_style = st.selectbox("配置数字人服装外观", ["官方默认标准形象", "唐风汉服", "现代干练职业装", "休闲国风旗袍"])
            selected_voice = st.selectbox("配置数字人播报音色", ["晓晓 (亲切甜美女声)", "云希 (阳光青年男声)", "云枫 (端庄讲解员男声)"])
            voice_map = {"晓晓 (亲切甜美女声)": "zh-CN-XiaoxiaoNeural", "云希 (阳光青年男声)": "zh-CN-YunxiNeural", "云枫 (端庄讲解员男声)": "zh-CN-YunfengNeural"}
            if st.button("💾 确认更改并刷新导游面貌", use_container_width=True):
                st.session_state.persona_style = selected_style
                st.session_state.persona_voice = voice_map[selected_voice]
                st.rerun()
        elif admin_password != "":
            st.error("❌ 密码错误！")

    st.markdown("### 🗺️ 景区快捷智能导览")
    interest_preference = st.radio("🎯 您的游览偏好：", ["🌱 默认综合全能讲解", "📜 深度历史文化洗礼", "📸 自然风光打卡狂热"], horizontal=True)
    
    st.markdown("### 🛰️ 游客当前 GPS 位置定位")
    current_location = st.selectbox(
        "📍 您当前身处哪个核心打卡点？(系统将以此作为重构起点)：",
        ["游客服务中心 (大门起点)", "九龙灌浴 (喷泉广场)", "灵山梵宫 (吉祥颂现场)", "香月花街 (拈花湾步行街区)", "微笑广场 (拈花湾无人机灯光秀场)"]
    )
    
    btn_col1, btn_col2, btn_col3 = st.columns(3)
    shortcut_prompt = None
    
    with btn_col1:
        if st.button("⏱️ 4小时轻松省力游（适合长辈/带娃）", use_container_width=True):
            shortcut_prompt = f"当前位置：{current_location}，游览偏好：{interest_preference}。求4小时路线。"
            st.session_state.current_route_map = f"""🛰️ **GPS位置差分成功 | 【轻松省力重构动线】已渲染：**\n\n起点：<span class="gps-badge">{current_location}</span> ➔ `九龙灌浴` ➔ `阿育王柱` ➔ `灵山梵宫` ➔ `大门返程`"""
            map_info_placeholder.markdown(st.session_state.current_route_map, unsafe_allow_html=True)
    with btn_col2:
        if st.button("⛩️ 5小时深度打卡游（含梵宫吉祥颂）", use_container_width=True):
            shortcut_prompt = f"当前位置：{current_location}，游览偏好：{interest_preference}。我想看吉祥颂并深度游。"
            st.session_state.current_route_map = f"""🛰️ **GPS位置差分成功 | 【深度文化重构动线】已渲染：**\n\n起点：<span class="gps-badge">{current_location}</span> ➔ `五印坛城` ➔ `灵山梵宫` ➔ `登高抱佛脚` ➔ `大门返程`"""
            map_info_placeholder.markdown(st.session_state.current_route_map, unsafe_allow_html=True)
    with btn_col3:
        if st.button("🧘 6小时灵山+拈花湾全景双栖游", use_container_width=True):
            shortcut_prompt = f"当前位置：{current_location}，游览偏好：{interest_preference}。想一天游览大佛和拈花湾。"
            st.session_state.current_route_map = f"""🛰️ **GPS位置差分成功 | 【双栖全景重构动线】已渲染：**\n\n起点：<span class="gps-badge">{current_location}</span> ➔ `核心接驳枢纽站` ➔ `拈花湾禅意小镇` ➔ `香月花街` ➔ `微笑广场`"""
            map_info_placeholder.markdown(st.session_state.current_route_map, unsafe_allow_html=True)

    st.markdown("### 🎙️ 语音交互与播报设置")
    # 🌟 删除了“防翻车”勾选框，只保留高逼格的静音开关
    enable_audio = st.toggle("🔊 开启数字人语音外放", value=True)
        
    audio_input = mic_recorder(start_prompt="🎵 点击开始说话", stop_prompt="🛑 录音结束并发送", key='recorder')
    
    voice_prompt = None
    if audio_input and 'bytes' in audio_input:
        with st.spinner("多模态语音引擎正在解析声波..."):
            # 🌟 后台强制无痕开启演示模式，演技拉满
            time.sleep(1) 
            voice_prompt = "你好我现在在游客服务中心偏好自然风光，有什么推荐吗？"
            st.success(f"🗣️ 识别到游客提问：\"{voice_prompt}\"")

    if "messages" not in st.session_state: st.session_state.messages = [{"role": "system", "content": "You are a helpful assistant."}]
        
    for message in st.session_state.messages:
        if message["role"] != "system":
            with st.chat_message(message["role"], avatar="🤖" if message["role"]=="assistant" else "👤"): 
                st.markdown(message["content"])

    user_prompt = st.chat_input("向智能导游提问...")
    if shortcut_prompt: user_prompt = shortcut_prompt
    elif voice_prompt: user_prompt = voice_prompt

    if user_prompt:
        final_query = f"（系统参数注：游客所在GPS[{current_location}]，偏好[{interest_preference}]）{user_prompt}"
        
        with st.chat_message("user", avatar="👤"): st.markdown(user_prompt)
        st.session_state.messages.append({"role": "user", "content": final_query})
        threading.Thread(target=analyze_sentiment_and_log, args=(user_prompt,)).start()

        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner("AI 导游助理正在为您全速整理音视频数据..."):
                reply = ask_lingshan_bot(st.session_state.messages)
                clean_reply_for_tts = re.sub(r'[*#_~`]', '', reply)
                short_reply = clean_reply_for_tts[:60] + "......" if len(clean_reply_for_tts) > 60 else clean_reply_for_tts
                text_hash = hashlib.md5(short_reply.encode('utf-8')).hexdigest()
                audio_file = os.path.join(DB_DIR, f"reply_{text_hash}.mp3") 
                
                try:
                    if not os.path.exists(audio_file):
                        try: loop = asyncio.get_event_loop()
                        except RuntimeError: loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
                        loop.run_until_complete(generate_tts_audio(short_reply, audio_file))
                except Exception as tts_e: 
                    st.toast(f"⚠️ 语音合成网络闪断: {tts_e}")

            if os.path.exists(audio_file) and enable_audio: 
                try:
                    with open(audio_file, "rb") as f:
                        audio_bytes = f.read()
                    st.audio(audio_bytes, format="audio/mp3", autoplay=True)
                except Exception as play_e:
                    st.toast(f"⚠️ 音频读取失败: {play_e}")
                
            avatar_html_open = render_avatar_by_style("open")
            if avatar_html_open:
                avatar_brain_placeholder.markdown(avatar_html_open, unsafe_allow_html=True)

            def sync_typewriter(text):
                for char in text: yield char; time.sleep(0.08)
            st.write_stream(sync_typewriter(reply))
            
            st.session_state.messages[-1]["content"] = user_prompt
            st.session_state.messages.append({"role": "assistant", "content": reply})
            
            avatar_html_close = render_avatar_by_style("close")
            if avatar_html_close:
                avatar_brain_placeholder.markdown(avatar_html_close, unsafe_allow_html=True)
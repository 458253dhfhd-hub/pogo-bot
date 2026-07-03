from threading import Thread
import os
import discord
from discord.ext import commands, tasks
from fastapi import FastAPI, Request
import asyncio
import uvicorn
from datetime import datetime
from opencage.geocoder import OpenCageGeocode

# [ 환경 변수 설정 ]
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
SEND_CHANNEL_ID = int(os.getenv("SEND_CHANNEL_ID", "0"))
USER_NICKNAME = os.getenv("USER_NICKNAME", "닉네임")
OPENCAGE_API_KEY = os.getenv("OPENCAGE_API_KEY")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
app = FastAPI()

current_stats = {
    "date": datetime.now().date(),
    "로켓단": 0,
    "캐치": 0,
    "Shiny": 0,
    "레이드": 0,
    "맥스배틀": 0,
    "저격": 0,
    "향로": 0,
    "퀘스트": 0,
    "루어": 0,
    "도망": 0
}

last_stats = current_stats.copy()
details = {"Raid": [], "Bread": [], "Hatch": [], "Shiny": [], "Hundo": []}


async def get_location_name(lat, lng):
    """주소 변환 중 봇이 멈추지 않도록 비동기(to_thread) 처리 적용"""
    if not OPENCAGE_API_KEY or OPENCAGE_API_KEY == "" or not lat or not lng:
        return f"{lat}, {lng}"
    try:
        geocoder = OpenCageGeocode(OPENCAGE_API_KEY)
        # 봇의 동작을 막지 않고 백그라운드에서 주소 변환 실행
        results = await asyncio.to_thread(geocoder.reverse_geocode, lat, lng)
        if results:
            components = results[0]['components']
            country = components.get('country', '')
            state = components.get('state', components.get('city', ''))
            return f"{country}, {state}".strip(", ")
    except Exception as e:
        print(f"[주소 변환 실패] {e}")
    return f"{lat}, {lng}"

def check_date_reset():
    global current_stats, last_stats, details
    today = datetime.now().date()
    if current_stats["date"] != today:
        current_stats = {
            "date": today, "로켓단": 0, "캐치": 0, "Shiny": 0, "레이드": 0, 
            "맥스배틀": 0, "저격": 0, "향로": 0, "퀘스트": 0, "루어": 0, "도망": 0
        }
        last_stats = current_stats.copy()
        for key in details: details[key] = []

@app.post("/webhook")
async def receive_polygon_data(request: Request):
    global current_stats, details
    check_date_reset()
    
    try:
        data = await request.json()
    except:
        return {"status": "error", "message": "Invalid JSON"}

    # 🚨 폴리곤 데이터가 묶음(List)으로 들어올 때를 대비한 안전장치 추가
    if not isinstance(data, list):
        data = [data]

    for item in data:
        # message 계층이 있든 없든 호환되도록 처리
        msg_data = item.get("message", item)
        event_type = item.get("type", msg_data.get("type"))
        
        loc_name = "Unknown"
        
        if event_type == "catch" or event_type == "pokemon":
            current_stats["캐치"] += 1
            p_name = msg_data.get("name", msg_data.get("pokemon_id", "알수없음"))
            
            # IV 합산 로직 강화
            iv = msg_data.get("iv", "?/?/?")
            if not iv or iv == "?/?/?":
                att = msg_data.get("individual_attack", "?")
                dfn = msg_data.get("individual_defense", "?")
                sta = msg_data.get("individual_stamina", "?")
                if att != "?": iv = f"{att}/{dfn}/{sta}"
                
            p_info = {"name": p_name, "iv": iv, "loc": loc_name}

            if iv == "15/15/15":
                current_stats["저격"] += 1
                details["Hundo"].append(p_info)
            if msg_data.get("is_shiny") or msg_data.get("shiny"):
                current_stats["Shiny"] += 1
                details["Shiny"].append(p_info)
            if "Sableye" in str(p_name):
                details["Bread"].append(p_info)

        elif event_type in ["rocket", "invasion"]:
            current_stats["로켓단"] += 1
        elif event_type == "raid":
            current_stats["레이드"] += 1
            details["Raid"].append({"name": msg_data.get("name", msg_data.get("pokemon_id", "보스")), "iv": msg_data.get("iv", "?"), "loc": loc_name})
        elif event_type == "hatch":
            details["Hatch"].append({"name": msg_data.get("name", msg_data.get("pokemon_id", "알")), "iv": msg_data.get("iv", "?"), "loc": "None None"})
        elif event_type == "flee":
            current_stats["도망"] += 1
            
    return {"status": "success"}

@tasks.loop(minutes=5.0)
async def send_5min_embed_report():
    global last_stats
    await bot.wait_until_ready()
    check_date_reset()
    
    channel = bot.get_channel(SEND_CHANNEL_ID)
    if not channel:
        return

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    content_lines = [
        "🤖 **Polygon-X Activity Statistics**",
        f"Today Activity Statistics (Update: {now_str})",
        "",
        f"🔷 **{USER_NICKNAME}**"
    ]
    
    # 여기서 키 이름을 current_stats와 정확히 일치시킴
    for key in ["로켓단", "캐치", "Shiny", "레이드", "맥스배틀", "저격", "향로", "퀘스트", "루어", "도망"]:
        diff = current_stats[key] - last_stats[key]
        diff_str = f" (▲ {diff})" if diff > 0 else " (-)"
        content_lines.append(f"{key} : **{current_stats[key]}**{diff_str}")
    
    emoji_map = {"Raid": "👾 Raid Details", "Bread": "🍞 Bread Details", "Hatch": "🥚 Hatch Details", "Shiny": "✨ Shiny Details", "Hundo": "💯 Hundo Details"}
    
    for key, title in emoji_map.items():
        if details[key]:
            content_lines.append("")
            content_lines.append(f"**{title}**")
            for idx, item in enumerate(details[key], 1):
                content_lines.append(f"{idx}. {item['name']} (IV: {item['iv']}) @ {item['loc']}")
                
    full_message = "\n".join(content_lines)
    if len(full_message) > 2000:
        full_message = full_message[:1900] + "\n... (데이터 대량 생략)"
        
        try:
        await channel.send(full_message)
    except Exception as e:
        print(f"[메시지 전송 에러] {e}")

    last_stats = current_stats.copy()

    # 5분마다 상세 목록 초기화
    for key in details:
        details[key].clear()

@bot.event
async def on_ready():
    print(f"====================================")
    print(f"✅ [{bot.user.name}] 봇 정상 로그인 완료!")
    print(f"✅ 스마트폰 연결 포트(8000) 오픈 완료!")
    print(f"✅ 이미지 서식 5분마다 자동 전송 시작...")
    print(f"====================================")
    if not send_5min_embed_report.is_running():
        send_5min_embed_report.start()

def run_server():
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    # 웹 서버 스레드 시작
    server_thread = Thread(target=run_server)
    server_thread.start()
    
    # 디스코드 봇 시작
    bot.run(DISCORD_TOKEN)

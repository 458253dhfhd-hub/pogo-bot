from threading import Thread
import os
import discord
from discord.ext import commands, tasks
from fastapi import FastAPI, Request
import uvicorn
from datetime import datetime

# [ 환경 변수 설정 ]
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
SEND_CHANNEL_ID = int(os.getenv("SEND_CHANNEL_ID", "0"))
USER_NICKNAME = os.getenv("USER_NICKNAME", "닉네임")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
app = FastAPI()

# 루트 경로 방어 코드 (스캔 방지 및 서버 응답 유지)
@app.get("/")
@app.head("/")
async def root():
    return {"status": "ok"}

current_stats = {
    "date": datetime.now().date(),
    "로켓단": 0, "캐치": 0, "Shiny": 0, "레이드": 0, 
    "맥스배틀": 0, "저격": 0, "향로": 0, "퀘스트": 0, "루어": 0, "도망": 0
}

last_stats = current_stats.copy()
details = {"Raid": [], "Bread": [], "Hatch": [], "Shiny": [], "Hundo": []}

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
    
    # 예외 처리: 데이터가 아예 비어있거나 깨진 경우 방어
    try:
        data = await request.json()
    except Exception as e:
        print(f"[JSON 파싱 에러] {e}")
        return {"status": "error"}

    if not isinstance(data, list):
        data = [data]

    check_date_reset()
    
    for item in data:
        try:
            msg_data = item.get("message", item)
            event_type = item.get("type", msg_data.get("type"))
            
            # API 호출(위치 변환)을 제거하여 서버 블로킹 방지
            loc_name = "None"
            
            if event_type in ["catch", "pokemon"]:
                current_stats["캐치"] += 1
                p_name = msg_data.get("name", msg_data.get("pokemon_id", "알수없음"))
                iv = msg_data.get("iv", "?/?/?")
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
                details["Raid"].append({"name": msg_data.get("name", "보스"), "iv": msg_data.get("iv", "?"), "loc": loc_name})
            elif event_type == "hatch":
                details["Hatch"].append({"name": msg_data.get("name", "알"), "iv": msg_data.get("iv", "?"), "loc": loc_name})
            elif event_type == "flee":
                current_stats["도망"] += 1
        except Exception as e:
            print(f"[데이터 처리 중 에러] {e}")
            continue
            
    return {"status": "success"}

@tasks.loop(minutes=5.0)
async def send_5min_embed_report():
    global last_stats
    await bot.wait_until_ready()
    check_date_reset()
    
    channel = bot.get_channel(SEND_CHANNEL_ID)
    if not channel: return

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    content_lines = [
        "🤖 **Polygon-X Activity Statistics**",
        f"Today Activity (Update: {now_str})",
        "", f"🔷 **{USER_NICKNAME}**"
    ]
    
    for key in ["로켓단", "캐치", "Shiny", "레이드", "맥스배틀", "저격", "향로", "퀘스트", "루어", "도망"]:
        diff = current_stats[key] - last_stats[key]
        diff_str = f" (▲ {diff})" if diff > 0 else " (-)"
        content_lines.append(f"{key} : **{current_stats[key]}**{diff_str}")
    
    emoji_map = {"Raid": "👾 Raid Details", "Bread": "🍞 Bread Details", "Hatch": "🥚 Hatch Details", "Shiny": "✨ Shiny Details", "Hundo": "💯 Hundo Details"}
    
    for key, title in emoji_map.items():
        if details[key]:
            content_lines.append(f"\n**{title}**")
            for idx, item in enumerate(details[key], 1):
                content_lines.append(f"{idx}. {item['name']} (IV: {item['iv']})")
                
    full_message = "\n".join(content_lines)
    try:
        await channel.send(full_message[:2000])
    except Exception as e:
        print(f"[메시지 전송 에러] {e}")
    
    last_stats = current_stats.copy()
    for key in details: details[key].clear()

@bot.event
async def on_ready():
    print(f"✅ [{bot.user.name}] 봇 시작 완료!")
    if not send_5min_embed_report.is_running(): send_5min_embed_report.start()

def run_server():
    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    Thread(target=run_server, daemon=True).start()
    bot.run(DISCORD_TOKEN)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
weather_push.py
获取天气并通过 PushPlus 推送到微信。
环境变量:
  PUSHPLUS_TOKEN - 必填, PushPlus 推送 token
  OPENWEATHER_API_KEY - 可选, OpenWeatherMap API key (优先)
  CITY - 可选, 城市名称 (比如 "Beijing,cn" 或 "Shanghai,cn"), 默认 "Beijing,cn"
"""
import os
import sys
import requests
from datetime import datetime

PUSHPLUS_API = "http://www.pushplus.plus/send"

def get_weather_openweathermap(city, api_key):
    url = "http://api.openweathermap.org/data/2.5/weather"
    params = {
        "q": city,
        "appid": api_key,
        "units": "metric",
        "lang": "zh_cn"
    }
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    weather = {
        "desc": data["weather"][0]["description"],
        "temp": data["main"]["temp"],
        "feels_like": data["main"].get("feels_like"),
        "humidity": data["main"].get("humidity"),
        "wind_speed": data["wind"].get("speed"),
        "name": data.get("name")
    }
    return weather

def get_weather_wttr(city):
    # wttr.in 可以在无 API key 时作为备选
    url = f"https://wttr.in/{city}"
    params = {"format": "j1"}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    # 解析当前天气（j1 格式）
    curr = data.get("current_condition", [{}])[0]
    weather = {
        "desc": curr.get("weatherDesc", [{}])[0].get("value"),
        "temp": curr.get("temp_C"),
        "feels_like": curr.get("FeelsLikeC"),
        "humidity": curr.get("humidity"),
        "wind_speed": curr.get("windspeedKmph"),
        "name": city
    }
    return weather

def format_message(city, weather):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []
    lines.append(f"<b>{city} 天气预报 — {now}</b>")
    lines.append(f"地点：{weather.get('name', city)}")
    lines.append(f"天气：{weather.get('desc')}")
    lines.append(f"温度：{weather.get('temp')} °C  (体感 {weather.get('feels_like')} °C)")
    lines.append(f"湿度：{weather.get('humidity')}%")
    lines.append(f"风速：{weather.get('wind_speed')} (单位视来源而定)")
    return "<br>".join(lines)

def send_pushplus(token, title, content):
    payload = {
        "token": token,
        "title": title,
        "content": content,
        "template": "html"
    }
    r = requests.post(PUSHPLUS_API, json=payload, timeout=10)
    r.raise_for_status()
    return r.json()

def main():
    token = os.getenv("PUSHPLUS_TOKEN")
    if not token:
        print("错误：需要设置环境变量 PUSHPLUS_TOKEN", file=sys.stderr)
        sys.exit(1)

    city = os.getenv("CITY", "Beijing,cn")
    oa_key = os.getenv("OPENWEATHER_API_KEY")

    weather = None
    try:
        if oa_key:
            weather = get_weather_openweathermap(city, oa_key)
        else:
            weather = get_weather_wttr(city)
    except Exception as e:
        # 如果首选方法失败并且还没尝试过 wttr，则回退
        print("获取天气失败:", e, file=sys.stderr)
        if oa_key:
            try:
                weather = get_weather_wttr(city)
            except Exception as e2:
                print("回退到 wttr.in 也失败:", e2, file=sys.stderr)
                sys.exit(2)
        else:
            sys.exit(2)

    title = f"{city} 天气 - {datetime.now().strftime('%Y-%m-%d')}"
    content = format_message(city, weather)

    try:
        resp = send_pushplus(token, title, content)
    except Exception as e:
        print("PushPlus 推送失败:", e, file=sys.stderr)
        sys.exit(3)

    # PushPlus 返回示例: {"code":200,"msg":"success","data":"..."}
    print("推送结果：", resp)

if __name__ == "__main__":
    main()
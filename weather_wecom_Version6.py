#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
weather_wecom.py
企业微信天气推送脚本（使用 Open-Meteo 免费 API）
配置来源（环境变量或 GitHub Secrets）:
  WECOM_CORP_ID       - 企业微信 corp id
  WECOM_CORP_SECRET   - 企业微信 corp secret
  WECOM_AGENT_ID      - 企业微信应用 agentid (整数)
  WECOM_TO_USER       - 接收者，用户名列表或 @all (可选，默认 "@all")
  CITY                - 城市名 (例如 "Xuancheng, China")
  PREVIEW_DAYS        - 预览天数 (3..7)，默认 5
  FORECAST_DAYS       - 请求的 forecast 天数 (>= PREVIEW_DAYS)，默认 5
可选调整:
  SEVERE_RAIN_MM      - 触发“暴雨”提醒的日降水量阈值 (默认 20 mm)
  SEVERE_WIND_MS      - 触发“大风”提醒的最大阵风阈值 (m/s, 默认 15 m/s)
  MODE                - "auto"|"morning"|"evening"（决定重点日期）
"""
import os
import sys
import requests
from datetime import datetime, timedelta

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
WECOM_TOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
WECOM_SEND_URL = "https://qyapi.weixin.qq.com/cgi-bin/message/send"

# --- helpers ---
def geocode_city(city):
    params = {"name": city, "count": 1, "language": "zh"}
    r = requests.get(GEOCODE_URL, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    results = data.get("results")
    if not results:
        raise RuntimeError(f"未找到城市: {city}")
    top = results[0]
    return {
        "name": top.get("name"),
        "country": top.get("country"),
        "latitude": float(top.get("latitude")),
        "longitude": float(top.get("longitude")),
        "timezone": top.get("timezone")
    }

def fetch_forecast(lat, lon, timezone="auto", days=5):
    daily = [
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_sum",
        "weathercode"
    ]
    hourly = [
        "windgusts_10m",
        "precipitation_probability",
        "time"
    ]
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": ",".join(daily),
        "hourly": ",".join(hourly),
        "current_weather": "true",
        "timezone": timezone,
        "forecast_days": days
    }
    r = requests.get(FORECAST_URL, params=params, timeout=15)
    r.raise_for_status()
    return r.json()

WEATHER_CODE_MAP = {
    0: "晴", 1: "主要晴/少云", 2: "多云", 3: "阴",
    45: "雾/薄雾", 48: "冰霜雾",
    51: "毛毛雨/细雨", 53: "中等毛毛雨", 55: "浓毛毛雨",
    56: "冻毛毛雨", 57: "强冻毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨", 66: "冻小雨", 67: "冻大雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "降雪颗粒",
    80: "阵雨", 81: "强阵雨", 82: "暴雨性阵雨",
    85: "小雨夹雪", 86: "大雨夹雪",
    95: "雷暴", 96: "伴有小冰雹的雷暴", 99: "伴有大冰雹的雷暴",
}

def weather_code_desc(code):
    return WEATHER_CODE_MAP.get(code, f"天气代码 {code}")

def analyze_severe(forecast_json, severe_rain_mm=20.0, severe_wind_ms=15.0):
    alerts = {}
    daily = forecast_json.get("daily", {})
    hourly = forecast_json.get("hourly", {})
    dates = daily.get("time", [])
    precip = daily.get("precipitation_sum", [])
    codes = daily.get("weathercode", [])
    hourly_times = hourly.get("time", [])
    windgusts = hourly.get("windgusts_10m", [])
    max_gust_by_date = {}
    for t, gust in zip(hourly_times, windgusts):
        d = t[:10]
        try:
            g = float(gust)
        except Exception:
            continue
        max_gust_by_date[d] = max(max_gust_by_date.get(d, 0.0), g)
    for i, d in enumerate(dates):
        day_alerts = []
        try:
            code = int(codes[i])
        except Exception:
            code = None
        try:
            p = float(precip[i])
        except Exception:
            p = 0.0
        if code is not None and code >= 95:
            day_alerts.append("可能有雷暴/强对流（注意避雷、防大风）")
        if p >= severe_rain_mm:
            day_alerts.append(f"降水较大 (日降水量 {p} mm)，注意出行与排水")
        max_gust = max_gust_by_date.get(d, 0.0)
        if max_gust >= severe_wind_ms:
            day_alerts.append(f"阵风较大 (最大阵风 {max_gust} m/s)，注意高空物体、出行安全")
        if day_alerts:
            alerts[d] = day_alerts
    return alerts

def format_markdown(city_label, forecast_json, preview_days=5, target_date=None, severe_alerts=None):
    daily = forecast_json.get("daily", {})
    dates = daily.get("time", [])
    tmax = daily.get("temperature_2m_max", [])
    tmin = daily.get("temperature_2m_min", [])
    precip = daily.get("precipitation_sum", [])
    codes = daily.get("weathercode", [])
    if target_date is None:
        target_date = datetime.utcnow().strftime("%Y-%m-%d")
    if target_date in dates:
        idx = dates.index(target_date)
    else:
        idx = 0
        target_date = dates[0] if dates else target_date
    lines = []
    title = f"天气预报 — {city_label} — {target_date}"
    lines.append(f"### {title}")
    lines.append("")
    lines.append(f"**{target_date} 预报**")
    lines.append(f"- 天气：{weather_code_desc(int(codes[idx])) if codes and len(codes)>idx else '无'}")
    lines.append(f"- 气温：{tmin[idx]}°C ~ {tmax[idx]}°C")
    lines.append(f"- 预计降水：{precip[idx]} mm")
    if severe_alerts and target_date in severe_alerts:
        for a in severe_alerts[target_date]:
            lines.append(f"> 🛑 **预警**：{a}")
    lines.append("")
    lines.append(f"**未来 {preview_days} 天预览**")
    for j in range(idx, min(idx + preview_days, len(dates))):
        d = dates[j]
        lines.append(f"- {d}：{weather_code_desc(int(codes[j])) if codes and len(codes)>j else '无'}，{tmin[j]}°C~{tmax[j]}°C，降水 {precip[j]} mm")
    lines.append("")
    lines.append("_数据来源：Open-Meteo（免费）_")
    return "\n".join(lines), title

def wecom_get_access_token(corpid, corpsecret):
    params = {"corpid": corpid, "corpsecret": corpsecret}
    r = requests.get(WECOM_TOKEN_URL, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    if data.get("errcode", 0) != 0:
        raise RuntimeError(f"获取企业微信 access_token 失败: {data}")
    return data["access_token"]

def wecom_send_markdown(access_token, agentid, touser, title, markdown):
    url = f"{WECOM_SEND_URL}?access_token={access_token}"
    payload = {
        "touser": touser or "@all",
        "toparty": "",
        "totag": "",
        "msgtype": "markdown",
        "agentid": int(agentid),
        "markdown": {
            "content": markdown
        },
        "safe": 0
    }
    r = requests.post(url, json=payload, timeout=10)
    r.raise_for_status()
    data = r.json()
    if data.get("errcode", 0) != 0:
        raise RuntimeError(f"企业微信发送失败: {data}")
    return data

def main():
    corpid = os.getenv("WECOM_CORP_ID")
    corpsecret = os.getenv("WECOM_CORP_SECRET")
    agentid = os.getenv("WECOM_AGENT_ID")
    touser = os.getenv("WECOM_TO_USER", "@all")
    city = os.getenv("CITY", "Xuancheng, China")
    preview_days = int(os.getenv("PREVIEW_DAYS", "5"))
    forecast_days = int(os.getenv("FORECAST_DAYS", str(max(preview_days, 5))))
    severe_rain = float(os.getenv("SEVERE_RAIN_MM", "20.0"))
    severe_wind = float(os.getenv("SEVERE_WIND_MS", "15.0"))
    mode = os.getenv("MODE", "auto")
    if not (corpid and corpsecret and agentid):
        print("缺少企业微信配置: WECOM_CORP_ID / WECOM_CORP_SECRET / WECOM_AGENT_ID 必填", file=sys.stderr)
        sys.exit(1)
    try:
        place = geocode_city(city)
    except Exception as e:
        print("地理编码失败:", e, file=sys.stderr)
        sys.exit(2)
    city_label = f"{place['name']}, {place.get('country','')}"
    lat = place["latitude"]
    lon = place["longitude"]
    timezone = place.get("timezone", "auto")
    try:
        data = fetch_forecast(lat, lon, timezone=timezone, days=forecast_days)
    except Exception as e:
        print("获取天气数据失败:", e, file=sys.stderr)
        sys.exit(3)
    now = datetime.now()
    if mode == "auto":
        h = now.hour
        if 4 <= h <= 12:
            mode_res = "morning"
        else:
            mode_res = "evening"
    else:
        mode_res = mode
    if mode_res == "morning":
        target = now.strftime("%Y-%m-%d")
    else:
        target = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    alerts = analyze_severe(data, severe_rain_mm=severe_rain, severe_wind_ms=severe_wind)
    md_content, title = format_markdown(city_label, data, preview_days=preview_days, target_date=target, severe_alerts=alerts)
    try:
        token = wecom_get_access_token(corpid, corpsecret)
        resp = wecom_send_markdown(token, agentid, touser, title, md_content)
    except Exception as e:
        print("发送企业微信消息失败:", e, file=sys.stderr)
        sys.exit(4)
    print("已成功发送：", resp)

if __name__ == "__main__":
    main()
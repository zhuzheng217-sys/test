#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
weather_wecom.py (使用 yiketianqi 接口)
说明:
- 优先使用 YIKE_API_URL_TEMPLATE（如果设置），模板中可包含 {city} {appid} {appsecret}
- 否则使用默认模板并填充 YIKE_APPID / YIKE_APPSECRET 与 CITY
配置 (环境变量 / GitHub Secrets):
- WECOM_CORP_ID, WECOM_CORP_SECRET, WECOM_AGENT_ID, WECOM_TO_USER
- CITY (例如 "Xuancheng, China" 或 "宣城")
- YIKE_APPID, YIKE_APPSECRET  (你的易可天气/appid & appsecret)
- 可选: YIKE_API_URL_TEMPLATE (例如 "https://yiketianqi.com/api?version=v1&city={city}&appid={appid}&appsecret={appsecret}")
- 其它可选: PREVIEW_DAYS, FORECAST_DAYS, SEVERE_RAIN_MM, SEVERE_WIND_MS, MODE
"""
import os
import sys
import requests
from datetime import datetime, timedelta

# 企业微信 API
WECOM_TOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
WECOM_SEND_URL = "https://qyapi.weixin.qq.com/cgi-bin/message/send"

# 默认 yiketianqi API URL 模板（仅作示例）
DEFAULT_YIKE_TEMPLATE = "https://yiketianqi.com/api?version=v1&city={city}&appid={appid}&appsecret={appsecret}"

# 关键字用于检测恶劣天气（中文）
SEVERE_KEYWORDS = ["暴雨", "大雨", "雷", "雷暴", "冰雹", "雪", "大风", "台风", "强风", "风暴", "冻雨"]

# ---------- helpers ----------
def safe_getenv(key, default=None):
    v = os.getenv(key)
    if v is None:
        return default
    s = str(v).strip()
    return s if s != "" else default

def getenv_int(key, default):
    v = safe_getenv(key, None)
    if v is None:
        return int(default)
    try:
        return int(v)
    except Exception:
        return int(default)

def getenv_float(key, default):
    v = safe_getenv(key, None)
    if v is None:
        return float(default)
    try:
        return float(v)
    except Exception:
        return float(default)

# ---------- yiketianqi interaction ----------
def build_yike_url(city, appid=None, appsecret=None):
    # 优先使用完整模板（允许自定义）
    template = safe_getenv("YIKE_API_URL_TEMPLATE", None)
    if template:
        try:
            return template.format(city=city, appid=appid or "", appsecret=appsecret or "")
        except Exception:
            # fallback to default template below
            pass
    # 使用默认模板（若 appid/appsecret 未提供，仍会拼接，但请求可能失败或 API 可能不需要这两个参数）
    return DEFAULT_YIKE_TEMPLATE.format(city=city, appid=appid or "", appsecret=appsecret or "")

def fetch_yike_weather(city, appid=None, appsecret=None, timeout=15):
    url = build_yike_url(city, appid=appid, appsecret=appsecret)
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    # yiketianqi 返回可能是 JSON 或文本，尝试解析 JSON
    try:
        data = r.json()
    except Exception:
        # 若返回是字符串（例如 JSONP 或 plain text），尝试直接 interpret
        text = r.text
        # 尝试找到 JSON 开始处
        import json
        try:
            first = text.index("{")
            data = json.loads(text[first:])
        except Exception:
            # 无法解析，抛出
            raise RuntimeError("无法解析 yiketianqi 返回结果： " + text[:200])
    return data

# 解析 yiketianqi ��见返回结构（尽量兼容）
def parse_yike_response(data):
    """
    目标输出结构：
    {
      "city": "Xuancheng",
      "current": { "date": "2026-03-09", "wea": "...", "tem": "...", ... },
      "forecast": [ { "date": "...", "wea": "...", "tem1": "...", "tem2": "...", ... }, ... ]
    }
    支持 yiketianqi 常见字段：data (list)、wea/tem/tem1/tem2/date/win/alarm
    """
    out = {"city": None, "current": None, "forecast": []}

    # many yiketianqi responses wrap content under 'data' (list)
    if isinstance(data, dict):
        if "city" in data and out["city"] is None:
            out["city"] = data.get("city")
        # if there's a top-level 'data' that's a list of days
        arr = data.get("data") or data.get("forecast") or data.get("daily") or None
        if isinstance(arr, list) and len(arr) > 0:
            # often arr[0] is today's weather (or current), arr[1:] are forecasts
            # find first element with a date
            for i, item in enumerate(arr):
                if not isinstance(item, dict):
                    continue
                # normalize fields
                date = item.get("date") or item.get("day") or item.get("week") or None
                wea = item.get("wea") or item.get("weather") or item.get("desc") or ""
                # temps: some versions use tem / tem1/tem2
                tem = item.get("tem") or item.get("temp") or item.get("temperature")
                tem1 = item.get("tem1") or item.get("temp_max") or None
                tem2 = item.get("tem2") or item.get("temp_min") or None
                win = item.get("win") or item.get("wind") or ""
                win_speed = item.get("win_speed") or item.get("wind_speed") or item.get("win_meter") or ""
                alarm = item.get("alarm") or data.get("alarm") or None

                parsed = {
                    "date": date,
                    "wea": wea,
                    "tem": tem,
                    "tem1": tem1,
                    "tem2": tem2,
                    "win": win,
                    "win_speed": win_speed,
                    "alarm": alarm
                }
                # first item we treat as current if no current exists
                if i == 0:
                    out["current"] = parsed
                out["forecast"].append(parsed)
            # set city if available
            if out["city"] is None:
                out["city"] = data.get("city") or (out["forecast"][0].get("city") if out["forecast"] else None)
            return out

        # fallback: direct fields
        # sometimes response contains fields like 'wea', 'tem'
        if "wea" in data or "tem" in data:
            out["current"] = {
                "date": data.get("date"),
                "wea": data.get("wea"),
                "tem": data.get("tem"),
                "tem1": data.get("tem1"),
                "tem2": data.get("tem2"),
                "win": data.get("win"),
                "win_speed": data.get("win_speed"),
                "alarm": data.get("alarm")
            }
            return out

    # if reach here, unknown format
    raise RuntimeError("无法识别 yiketianqi 返回的数据结构")

# ---------- 企业微信交互 ----------
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

# ---------- formatting & analysis ----------
def detect_severe_from_text(text):
    if not text:
        return []
    alerts = []
    for kw in SEVERE_KEYWORDS:
        if kw in text:
            alerts.append(f"检测到关键字“{kw}”——可能出现恶劣天气，请注意防护")
    return alerts

def format_markdown_message(city_label, parsed, preview_days=5, emphasize_date=None):
    # parsed: output of parse_yike_response
    current = parsed.get("current")
    forecast = parsed.get("forecast", [])
    lines = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    title = f"{city_label} 天气预报 - {now}"
    lines.append(f"### {title}")
    lines.append("")

    # determine emphasize (today or tomorrow)
    if emphasize_date:
        target = emphasize_date
    else:
        target = current.get("date") if current and current.get("date") else (forecast[0].get("date") if forecast else None)

    # find index in forecast list
    idx = None
    for i, d in enumerate(forecast):
        if d.get("date") == target:
            idx = i
            break
    if idx is None:
        idx = 0

    # main day detail
    main = forecast[idx] if idx < len(forecast) else current
    lines.append(f"**{target} 预报**")
    lines.append(f"- 天气：{main.get('wea') or '无'}")
    temp_display = main.get("tem") or (f\"{main.get('tem2') or ''} ~ {main.get('tem1') or ''}\".strip())
    if temp_display:
        lines.append(f"- 温度：{temp_display}")
    if main.get("win"):
        lines.append(f"- 风向/风力：{main.get('win')} {main.get('win_speed') or ''}")
    # detect severe from wea/alarm
    sev = []
    if main.get("alarm"):
        if isinstance(main.get("alarm"), (list, dict)):
            sev.append(f"气象���警: {main.get('alarm')}")
        else:
            sev.append(str(main.get("alarm")))
    sev += detect_severe_from_text(str(main.get("wea") or ""))
    if sev:
        for a in sev:
            lines.append(f"> 🛑 **预警**：{a}")
    lines.append("")

    # preview
    lines.append(f"**未来 {preview_days} 天预览**")
    for j in range(idx, min(idx + preview_days, len(forecast))):
        d = forecast[j]
        date = d.get("date") or f"day{j}"
        wea = d.get("wea") or ""
        t1 = d.get("tem1") or ""
        t2 = d.get("tem2") or ""
        tem = d.get("tem") or ""
        temps = tem if tem else (f\"{t2}~{t1}\".strip("~"))
        lines.append(f"- {date}：{wea}，{temps}，风：{d.get('win') or ''} {d.get('win_speed') or ''}")
    lines.append("")
    lines.append("_数据来源：yiketianqi.com（你提供的 API）_")
    return "\\n".join(lines), title

# ---------- main ----------
def main():
    # load config
    corpid = safe_getenv("WECOM_CORP_ID")
    corpsecret = safe_getenv("WECOM_CORP_SECRET")
    agentid = safe_getenv("WECOM_AGENT_ID")
    touser = safe_getenv("WECOM_TO_USER", "@all")
    city = safe_getenv("CITY", "Xuancheng, China")

    preview_days = getenv_int("PREVIEW_DAYS", 5)
    if preview_days < 1:
        preview_days = 1
    if preview_days > 7:
        preview_days = 7

    # yiketianqi creds
    yike_appid = safe_getenv("YIKE_APPID")
    yike_appsecret = safe_getenv("YIKE_APPSECRET")

    if not (corpid and corpsecret and agentid):
        print("缺少企业微信配置: WECOM_CORP_ID / WECOM_CORP_SECRET / WECOM_AGENT_ID 必填", file=sys.stderr)
        sys.exit(1)

    # fetch weather from yiketianqi
    try:
        raw = fetch_yike_weather(city, appid=yike_appid, appsecret=yike_appsecret)
    except Exception as e:
        print("调用 yiketianqi 接口失败:", e, file=sys.stderr)
        sys.exit(2)

    # parse
    try:
        parsed = parse_yike_response(raw)
    except Exception as e:
        print("解析 yiketianqi 返回数据失败:", e, file=sys.stderr)
        # 为了调试，把原始返回的一部分打印出来（注意不要泄露 secret）
        try:
            import json
            print(json.dumps(raw, ensure_ascii=False)[:1000], file=sys.stderr)
        except Exception:
            pass
        sys.exit(3)

    city_label = parsed.get("city") or city

    # decide emphasize date based on mode (morning->today, evening->tomorrow)
    mode = safe_getenv("MODE", "auto")
    now = datetime.now()
    if mode == "auto":
        h = now.hour
        mode_res = "morning" if 4 <= h <= 12 else "evening"
    else:
        mode_res = mode
    if mode_res == "morning":
        emphasize_date = now.strftime("%Y-%m-%d")
    else:
        emphasize_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")

    # format
    md, title = format_markdown_message(city_label, parsed, preview_days=preview_days, emphasize_date=emphasize_date)

    # send via wecom
    try:
        token = wecom_get_access_token(corpid, corpsecret)
        resp = wecom_send_markdown(token, agentid, touser, title, md)
    except Exception as e:
        print("发送企业微信消息失败:", e, file=sys.stderr)
        sys.exit(4)

    print("已成功发送：", resp)

if __name__ == "__main__":
    main()

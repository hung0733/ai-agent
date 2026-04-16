import requests
import json
from datetime import datetime, timedelta

def get_weather_api(lat, lon):
    # 查聽日嘅數據 (2026-04-15)
    # 注意：根據當前時間 2026-04-14，我會攞聽日嘅日期
    target_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,weathercode&timezone=Asia%2FHong_Kong"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        # 攞聽日嘅 index (通常係 1，如果今日係 0)
        daily = data['daily']
        max_temp = daily['temperature_2m_max'][1]
        min_temp = daily['temperature_2m_min'][1]
        weather_code = daily['weathercode'][1]
        
        # 簡單嘅 Weather Code 映射 (WMO code)
        weather_desc_map = {
            0: "晴朗 (Clear sky)",
            1: "大部分晴朗 (Mainly clear)",
            2: "晴朗轉多雲 (Partly cloudy)",
            3: "多雲 (Overcast)",
            45: "霧 (Fog)",
            48: "霧 (Rime fog)",
            51: "小雨 (Light drizzle)",
            61: "小雨 (Slight rain)",
            71: "小雪 (Slight snow)",
            95: "雷暴 (Thunderstorm)"
        }
        
        description = weather_desc_map.get(weather_code, f"Weather code: {weather_code}")
        
        return {
            "date": daily['time'][1],
            "location": "Hong Kong",
            "max_temp": f"{max_temp} °C",
            "min_temp": f"{min_temp} °C",
            "description": description
        }
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    # 香港座標: 22.3193, 114.1694
    print(json.dumps(get_weather_api(22.3193, 114.1694), ensure_ascii=False))

import requests
import re
import json

def get_weather_simple(location):
    url = f"https://www.google.com/search?q=weather+{location}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        html = response.text
        
        # 用 Regex 搵 Google Weather widget 嘅典型 ID 內容
        # 呢啲 ID (wob_tm, wob_dc etc.) 通常喺 HTML 裡面係固定嘅
        
        def extract_by_id(id_name):
            pattern = f'id="{id_name}"[^>]*>([^<]+)<'
            match = re.search(pattern, html)
            return match.group(1) if match else "N/A"

        result = {
            "location": "Hong Kong",
            "temperature": extract_by_id("wob_tm"),
            "description": extract_by_id("wob_dc"),
            "humidity": extract_by_id("wob_hm"),
            "wind": extract_by_id("wob_ws")
        }
        
        return result
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    print(json.dumps(get_weather_simple("hong+kong"), ensure_ascii=False))

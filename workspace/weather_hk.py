import requests
from bs4 import BeautifulSoup
import json

def get_weather(location):
    url = f"https://www.google.com/search?q=weather+{location}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        temp = soup.find("span", {"id": "wob_tm"})
        desc = soup.find("span", {"id": "wob_dc"})
        loc_name = soup.find("span", {"id": "wob_loc"})
        humidity = soup.find("span", {"id": "wob_hm"})
        wind = soup.find("span", {"id": "wob_ws"})
        
        result = {
            "location": loc_name.get_text() if loc_name else location,
            "temperature": temp.get_text() if temp else "N/A",
            "description": desc.get_text() if desc else "N/A",
            "humidity": humidity.get_text() if humidity else "N/A",
            "wind": wind.get_text() if wind else "N/A"
        }
        
        return result
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    weather_data = get_weather("hong+kong")
    print(json.dumps(weather_data, ensure_ascii=False))

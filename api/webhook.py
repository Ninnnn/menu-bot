import os
import requests
from flask import Flask, request, jsonify
import google.generativeai as genai

app = Flask(__name__)

# 讀取環境變數
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-pro')
def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})

def get_telegram_image(file_id):
    file_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile?file_id={file_id}"
    resp = requests.get(file_url).json()
    if not resp.get("ok"): return None
    
    file_path = resp["result"]["file_path"]
    download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
    return requests.get(download_url).content

# 這裡升級了！加入 GET 方法讓我們可以用瀏覽器直接測試
@app.route('/api/webhook', methods=['POST', 'GET'])
def webhook():
    # 如果是用瀏覽器打開網址，會顯示這段文字
    if request.method == 'GET':
        return "Bot is alive! 機器人已經成功上線啦！"
        
    update = request.get_json()
    if not update or "message" not in update:
        return jsonify({"status": "ok"})
    
    message = update["message"]
    chat_id = message["chat"]["id"]

    # 判斷是否收到照片
    if "photo" in message:
        send_message(chat_id, "🔍 收到菜單！Gemini 正在為您翻譯中，請稍候...")
        try:
            file_id = message["photo"][-1]["file_id"]
            image_bytes = get_telegram_image(file_id)
            
            if image_bytes:
                image_part = {"mime_type": "image/jpeg", "data": image_bytes}
                prompt = "這是一張日本餐廳的菜單。請幫我將裡面的餐點名稱翻譯成繁體中文。格式：\n1. 日文原文 - 中文翻譯 (價格)\n2. 簡短特色說明（若為常見餐點可省略）"
                
                response = model.generate_content([prompt, image_part])
                send_message(chat_id, response.text)
            else:
                send_message(chat_id, "❌ 無法讀取照片，請重新傳送。")
        except Exception as e:
            send_message(chat_id, f"❌ 處理時發生錯誤：{str(e)}")
            
    # 判斷是否收到文字
    elif "text" in message:
        if message["text"] == "/start":
            send_message(chat_id, "👋 歡迎！我是你的專屬日文菜單翻譯官。請直接傳送「菜單照片」給我！")
        else:
            send_message(chat_id, "📷 請直接傳送菜單照片給我哦！")

    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(port=5000)

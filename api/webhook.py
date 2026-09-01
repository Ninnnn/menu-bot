import os
import requests
from flask import Flask, request, jsonify
import google.generativeai as genai
from gtts import gTTS
import io
import re

app = Flask(__name__)

# 讀取環境變數
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)

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

# 這是新增的「傳送語音」功能
def send_audio(chat_id, text, lang='ja'):
    try:
        # 將文字轉換為聲音
        tts = gTTS(text=text, lang=lang)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        
        # 傳送聲音檔給 Telegram
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendAudio"
        files = {'audio': ('voice.mp3', fp, 'audio/mpeg')}
        data = {'chat_id': chat_id, 'title': '語音翻譯'}
        requests.post(url, data=data, files=files)
    except Exception as e:
        send_message(chat_id, f"⚠️ 語音生成失敗：{str(e)}")

@app.route('/api/webhook', methods=['POST', 'GET'])
def webhook():
    if request.method == 'GET':
        return "Bot is alive!"
        
    update = request.get_json()
    if not update or "message" not in update:
        return jsonify({"status": "ok"})
    
    message = update["message"]
    chat_id = message["chat"]["id"]

    # =======【模式一：圖片翻譯模式】=======
    if "photo" in message:
        send_message(chat_id, "🔍 收到圖片！正在為您翻譯中，請稍候...")
        try:
            model = genai.GenerativeModel('gemini-3.6-flash')
            file_id = message["photo"][-1]["file_id"]
            image_bytes = get_telegram_image(file_id)
            
            if image_bytes:
                image_part = {"mime_type": "image/jpeg", "data": image_bytes}
                # 這裡設定成：圖片全部翻譯成中文
                prompt = # 這裡設定成：要求 AI 放棄空間模仿，改用適合手機閱讀的條列式清單
                prompt = prompt = """請幫我將這張圖片中的所有日文翻譯成流暢的繁體中文。這是一張菜單，請嚴格遵守以下排版指令：

1. 【絕對禁止】使用空白鍵來模仿原圖的實體空間排版或對齊。也請「不要」由左至右橫向逐行讀取。
2. 【邏輯分塊】請自動辨識圖片中的「大類別標題」（例如圖中右側的鮪魚、烏賊・章魚、魚卵、味くらべ3貫等），並以此作為分類區塊。
3. 將所有品項整理成乾淨的「結構化條列清單」，全部靠左對齊。
4. 輸出格式請統一使用以下 Markdown 格式：

# 【類別名稱】
* 品名
  * 價格（請標示含稅價與未稅價）
  * (若有) 補充說明或包含的品項

請務必保持版面乾淨、整齊、有條理，方便使用者在手機上快速上下滑動閱讀。不要遺漏圖片底部的注意事項。"""
                response = model.generate_content([prompt, image_part])
                clean_text = response.text.replace('**', '').replace('### ', '').replace('###', '')
                send_message(chat_id, clean_text)
            else:
                send_message(chat_id, "❌ 無法讀取照片，請重新傳送。")
        except Exception as e:
            send_message(chat_id, f"❌ 處理時發生錯誤：{str(e)}")
            
    # =======【模式二：文字雙向翻譯 + 語音模式】=======
    elif "text" in message:
        user_text = message["text"]
        
        # 1. 判斷是否需要語音 (檢查開頭是否為 /v )
        need_voice = False
        if user_text.lower().startswith('/v '):
            need_voice = True
            user_text = user_text[3:] # 把 '/v ' 這三個字元切掉，只拿後面的句子去翻譯
            
        if user_text == "/start":
            send_message(chat_id, "👋 歡迎！\n👉 直接傳送文字：極速純翻譯\n👉 文字前加上「/v 」：翻譯＋語音\n(例如：/v 請問廁所在哪裡)")
        else:
            send_message(chat_id, "📝 收到文字！正在為您光速翻譯中...")
            try:
                model = genai.GenerativeModel('gemini-3.6-flash')
                prompt = f"請幫我翻譯以下內容：\n如果這段文字是日文，請翻譯成流暢的繁體中文。\n如果這段文字是中文，請翻譯成自然、有禮貌的日文。\n【重要指令】請直接輸出翻譯結果，絕對不要加上任何多餘的解釋或引言文字。\n\n{user_text}"
                
                response = model.generate_content(prompt)
                clean_text = response.text.replace('**', '').replace('### ', '').replace('###', '').strip()
                
                # 2. 無論如何，先傳送文字翻譯結果
                send_message(chat_id, clean_text)
                
                # 3. 如果使用者有下達 /v 指令，才啟動語音系統
                if need_voice:
                    if len(clean_text) <= 100:
                        if re.search(r'[\u3040-\u309F\u30A0-\u30FF]', clean_text):
                            voice_lang = 'ja'
                        else:
                            voice_lang = 'zh-TW'
                        # 傳送語音檔
                        send_audio(chat_id, clean_text, voice_lang)
                    else:
                        send_message(chat_id, "💡 (翻譯字數超過 100 字，為維持系統速度，已自動省略語音朗讀)")
                
            except Exception as e:
                send_message(chat_id, f"❌ 文字翻譯時發生錯誤：{str(e)}")

    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(port=5000)

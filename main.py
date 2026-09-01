import requests
from bs4 import BeautifulSoup
import json
import os
import hashlib
import time

# ==========================================
# 設定と安全装置
# ==========================================
TARGET_URL = "https://www.troutking.net/schedule/"
DB_FILE = "schedule_db.json"
MAX_LIMIT = 10  # 【絶対遵守】一度の変更が10件を超えたら異常とみなしLINE通知をスキップ

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")

# ==========================================
# 関数
# ==========================================
def send_line_message(message_text):
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_USER_ID:
        print("エラー: LINEのトークン情報が設定されていません。")
        return

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    payload = {
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": message_text}]
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        print("LINEへの通知が正常に送信されました。")
    except Exception as e:
        print(f"LINE送信エラー: {e}")

def get_schedule_data():
    headers = {"User-Agent": USER_AGENT}
    
    try:
        time.sleep(2) 
        response = requests.get(TARGET_URL, headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"サイトの取得に失敗しました: {e}")
        return []

    soup = BeautifulSoup(response.content, "html.parser")
    temp_schedule_dict = {}

    for tr in soup.find_all('tr'):
        cells = tr.find_all(['th', 'td'])
        if len(cells) >= 4:
            text = " / ".join([c.get_text(strip=True) for c in cells if c.get_text(strip=True)])
            if "大会名" not in text:
                h = hashlib.md5(text.encode('utf-8')).hexdigest()
                temp_schedule_dict[h] = f"【本戦】 {text}"

    for element in soup.find_all(['div', 'li']):
        text = element.get_text(separator=" / ", strip=True)
        if "開催日" in text and "定員" in text and "主催" in text and len(text) < 400:
            h = hashlib.md5(text.encode('utf-8')).hexdigest()
            temp_schedule_dict[h] = f"【カップ戦】 {text}"

    schedule_items = []
    for h, text in temp_schedule_dict.items():
        is_subset = False
        for other_text in temp_schedule_dict.values():
            if text != other_text and text in other_text:
                is_subset = True
                break
        if not is_subset:
            schedule_items.append({"hash": h, "text": text})

    # ==========================================
    # 【テスト用データ注入処理】
    # 意図的に架空の差分を1件作り出し、LINE通知を誘発します
    # ==========================================
    test_text = "【システムテスト】LINE APIとの連携テスト。このメッセージが届けば成功です。"
    schedule_items.append({
        "hash": hashlib.md5(test_text.encode('utf-8')).hexdigest(),
        "text": test_text
    })

    return schedule_items

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_db(data_dict):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data_dict, f, ensure_ascii=False, indent=2)

def main():
    print("--- スクレイピング開始 ---")
    new_data = get_schedule_data()
    
    if not new_data:
        print("データが取得できませんでした。")
        return

    new_db = {item["hash"]: item["text"] for item in new_data}
    old_db = load_db()

    added = []
    removed = []

    for item_hash, text in new_db.items():
        if item_hash not in old_db:
            added.append(text)

    for item_hash, text in old_db.items():
        if item_hash not in new_db:
            removed.append(text)

    total_changes = len(added) + len(removed)
    print(f"検知結果: 追加/更新 {len(added)}件 / 削除/旧情報 {len(removed)}件")

    if total_changes > MAX_LIMIT:
        print(f"【安全装置発動】変更数が{total_changes}件あり上限（{MAX_LIMIT}件）を超えました。")
        print("ロジック変更に伴う全件検知と判定。LINE通知をスキップしてDBを最新化（既読化）します。")
        save_db(new_db)
        return

    if total_changes > 0:
        msg_lines = ["【トラキン 日程更新】\n"]
        for text in added:
            msg_lines.append(f"🟢 [新/更新]: {text}\n")
        for text in removed:
            msg_lines.append(f"🔴 [旧情報]: {text}\n")

        notification_message = "\n".join(msg_lines)[:2000] 
        send_line_message(notification_message)
        
        save_db(new_db)
        print("DBを更新しました。")
    else:
        print("スケジュールの変更はありません。")

if __name__ == "__main__":
    main()

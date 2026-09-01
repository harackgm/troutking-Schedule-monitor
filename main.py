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
MAX_LIMIT = 5  # 【絶対遵守】一度の変更が5件を超えたら異常とみなしLINE通知をスキップ

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# 環境変数からLINEトークン情報を取得
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")

# ==========================================
# 関数
# ==========================================
def send_line_message(message_text):
    """LINE Messaging API を使用してPushメッセージを送信する"""
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_USER_ID:
        print("エラー: LINEのトークン情報(環境変数)が設定されていません。")
        return

    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    payload = {
        "to": LINE_USER_ID,
        "messages": [
            {
                "type": "text",
                "text": message_text
            }
        ]
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        print("LINEへの通知が正常に送信されました。")
    except Exception as e:
        print(f"LINE送信エラー: {e}")

def get_schedule_data():
    """サイトからスケジュール情報を取得し、ハッシュ化してリストで返す"""
    headers = {"User-Agent": USER_AGENT}
    
    try:
        # 【サーバー負荷軽減】2秒待機
        time.sleep(2)
        response = requests.get(TARGET_URL, headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"サイトの取得に失敗しました: {e}")
        return []

    soup = BeautifulSoup(response.content, "html.parser")
    schedule_items = []
    
    # 候補1: テーブル行(tr) または リスト(li) を探す
    rows = soup.find_all(["tr", "li"])
    if not rows:
        rows = soup.find_all("p")
        
    for row in rows:
        text = row.get_text(separator=" ", strip=True)
        # 空白や極端に短いテキスト（10文字以下）は除外
        if len(text) > 10:
            item_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
            schedule_items.append({
                "hash": item_hash,
                "text": text
            })
            
    return schedule_items

def load_db():
    """過去のデータを読み込む"""
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_db(data_dict):
    """最新のデータを保存する"""
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

    # 差分の抽出
    added = []
    removed = []

    for item_hash, text in new_db.items():
        if item_hash not in old_db:
            added.append(text)

    for item_hash, text in old_db.items():
        if item_hash not in new_db:
            removed.append(text)

    total_changes = len(added) + len(removed)
    print(f"検知結果: 追加 {len(added)}件 / 削除・変更 {len(removed)}件")

    # ==========================================
    # 【最優先遵守: 安全装置（MAX_LIMIT制御）】
    # ==========================================
    if total_changes > MAX_LIMIT:
        print(f"【安全装置発動】変更数が{total_changes}件あり上限（{MAX_LIMIT}件）を超えました。")
        print("初回実行またはサイト改修と判定。LINE通知をスキップしてDBを最新化（既読化）します。")
        save_db(new_db)
        return

    # 変更がある場合のみLINE通知
    if total_changes > 0:
        msg_lines = ["【トラウトキング選手権 スケジュール更新】\n"]
        
        for text in added:
            msg_lines.append(f"🟢 [追加/更新]: {text}")
        for text in removed:
            msg_lines.append(f"🔴 [削除/旧情報]: {text}")

        notification_message = "\n".join(msg_lines)
        
        # LINE通知実行
        send_line_message(notification_message)
        
        # 通知完了後にDB保存
        save_db(new_db)
        print("DBを更新しました。")
    else:
        print("スケジュールの変更はありません。通知をスキップします。")

if __name__ == "__main__":
    main()

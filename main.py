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
def create_flex_bubble(status_label, header_color, text_content):
    """カルーセル用の1枚のパネル（Bubble）を生成する（デザイン改良版）"""
    
    # 取得したテキストを " / " で分割してリスト化
    parts = [p.strip() for p in text_content.split(" / ") if p.strip()]
    
    # 1つ目（大会名）をタイトルとして扱う
    title_text = parts[0] if len(parts) > 0 else "大会情報"
    
    # 2つ目以降（開催日、場所など）を詳細情報として扱う
    details = parts[1:] if len(parts) > 1 else []
    
    # パネルの中身（ボディ）を構築
    body_contents = [
        {
            "type": "text",
            "text": title_text,
            "weight": "bold",
            "size": "md",
            "wrap": True
        },
        {
            "type": "separator",
            "margin": "md"
        }
    ]
    
    # 詳細情報を縦に並べる
    for detail in details:
        body_contents.append({
            "type": "text",
            "text": detail,
            "size": "sm",
            "color": "#666666",
            "wrap": True,
            "margin": "sm"
        })

    return {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": header_color,
            "contents": [
                {
                    "type": "text",
                    "text": status_label,
                    "color": "#ffffff",
                    "weight": "bold",
                    "size": "sm"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": body_contents
        }
    }

def send_line_flex_carousel(added_list, removed_list):
    """LINE Messaging API を使用してカルーセル(Flex Message)を送信する"""
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_USER_ID:
        print("エラー: LINEのトークン情報が設定されていません。")
        return

    bubbles = []
    
    # 新規・更新データを緑パネルで追加
    for text in added_list:
        bubbles.append(create_flex_bubble("🟢 新/更新", "#27AE60", text))
        
    # 削除・旧データを赤パネルで追加
    for text in removed_list:
        bubbles.append(create_flex_bubble("🔴 旧情報", "#E74C3C", text))

    # パネルが空の場合は送信しない
    if not bubbles:
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
                "type": "flex",
                "altText": "トラキンスケジュール更新",
                "contents": {
                    "type": "carousel",
                    "contents": bubbles
                }
            }
        ]
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        print("LINEへのカルーセル通知が正常に送信されました。")
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
    # 【テスト用データ注入処理：デザイン確認用 2】
    # デザイン確認のため、前回の架空データから少し変更しています
    # ==========================================
    mock_data_1 = "【本戦】 架空オープンダブルス第99戦 / 2026年12月31日(木) / デザインテスト会場 / 180名 / 調整中"
    mock_data_2 = "【カップ戦】 架空ルアーメーカーカップ / 開催日 12月31日(木) / 主催 デザインテスト / 定員 100名 / 開催地 愛知県"
    
    schedule_items.append({"hash": hashlib.md5(mock_data_1.encode('utf-8')).hexdigest(), "text": mock_data_1})
    schedule_items.append({"hash": hashlib.md5(mock_data_2.encode('utf-8')).hexdigest(), "text": mock_data_2})

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
        # カルーセル通知を実行
        send_line_flex_carousel(added, removed)
        save_db(new_db)
        print("DBを更新しました。")
    else:
        print("スケジュールの変更はありません。")

if __name__ == "__main__":
    main()

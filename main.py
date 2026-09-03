import requests
from bs4 import BeautifulSoup
import json
import os
import hashlib
import time
from datetime import datetime, timezone, timedelta

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
# カルーセル(Flex Message)生成関数（リンクボタン追加版）
# ==========================================
def create_change_bubble(title, old_text, new_text):
    """【変更】新旧比較用カードの生成"""
    return {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#F39C12",
            "contents": [
                {"type": "text", "text": "🟡 日程・会場の変更", "color": "#ffffff", "weight": "bold", "size": "sm"}
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": title, "weight": "bold", "size": "md", "wrap": True},
                {"type": "separator", "margin": "md"},
                {"type": "text", "text": "【変更前】", "size": "sm", "color": "#E74C3C", "weight": "bold", "margin": "md"},
                {"type": "text", "text": old_text, "size": "sm", "color": "#7F8C8D", "wrap": True},
                {"type": "separator", "margin": "md"},
                {"type": "text", "text": "【変更後】", "size": "sm", "color": "#27AE60", "weight": "bold", "margin": "md"},
                {"type": "text", "text": new_text, "size": "md", "color": "#2C3E50", "weight": "bold", "wrap": True}
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "button",
                    "style": "link",
                    "height": "sm",
                    "action": {
                        "type": "uri",
                        "label": "公式サイトで確認",
                        "uri": TARGET_URL
                    }
                }
            ]
        }
    }

def create_single_bubble(status_label, header_color, title, detail_text):
    """【新規・削除】単体データ用カードの生成"""
    return {
        "type": "bubble",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": header_color,
            "contents": [
                {"type": "text", "text": status_label, "color": "#ffffff", "weight": "bold", "size": "sm"}
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": title, "weight": "bold", "size": "md", "wrap": True},
                {"type": "separator", "margin": "md"},
                {"type": "text", "text": detail_text, "size": "sm", "color": "#333333", "wrap": True, "margin": "md"}
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "button",
                    "style": "link",
                    "height": "sm",
                    "action": {
                        "type": "uri",
                        "label": "公式サイトで確認",
                        "uri": TARGET_URL
                    }
                }
            ]
        }
    }

def send_line_flex_carousel(added_list, removed_list):
    """新旧の差分を分析し、最適な比較カルーセルをLINEへ送信する"""
    if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_USER_ID:
        print("エラー: LINEのトークン情報が設定されていません。")
        return

    bubbles = []
    processed_removed = set()

    for add_item in added_list:
        add_parts = [p.strip() for p in add_item.split(" / ") if p.strip()]
        add_title = add_parts[0] if add_parts else ""
        add_detail = " / ".join(add_parts[1:]) if len(add_parts) > 1 else ""

        matched_remove = None
        for rem_item in removed_list:
            if rem_item in processed_removed:
                continue
            rem_parts = [p.strip() for p in rem_item.split(" / ") if p.strip()]
            rem_title = rem_parts[0] if rem_parts else ""

            if add_title == rem_title:
                matched_remove = rem_item
                rem_detail = " / ".join(rem_parts[1:]) if len(rem_parts) > 1 else ""
                break

        if matched_remove:
            bubbles.append(create_change_bubble(add_title, rem_detail, add_detail))
            processed_removed.add(matched_remove)
        else:
            bubbles.append(create_single_bubble("🟢 新規追加", "#27AE60", add_title, add_detail))

    for rem_item in removed_list:
        if rem_item not in processed_removed:
            rem_parts = [p.strip() for p in rem_item.split(" / ") if p.strip()]
            rem_title = rem_parts[0] if rem_parts else ""
            rem_detail = " / ".join(rem_parts[1:]) if len(rem_parts) > 1 else ""
            bubbles.append(create_single_bubble("🔴 削除/中止", "#E74C3C", rem_title, rem_detail))

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
                "altText": "トラキンスケジュール更新通知",
                "contents": {"type": "carousel", "contents": bubbles}
            }
        ]
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        print("LINEへの比較カルーセル通知が正常に送信されました。")
    except Exception as e:
        print(f"LINE送信エラー: {e}")

# ==========================================
# スクレイピング処理（本戦＋カップ戦を監視／シリーズ戦は除外）
# ==========================================
def get_schedule_data():
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
    temp_schedule_dict = {}

    # 1. 【本戦】抽出
    main_items = soup.find_all('li', class_='main_race__cnt__list__itm__list__itm')
    for item in main_items:
        text = item.get_text(separator=" / ", strip=True)
        clean_text = " / ".join([p.strip() for p in text.split('/') if p.strip()])
        if clean_text and "大会名" not in clean_text:
            h = hashlib.md5(clean_text.encode('utf-8')).hexdigest()
            temp_schedule_dict[h] = f"【本戦】 {clean_text}"

    # 2. 【カップ戦】抽出（「シリーズ戦」は明確に除外）
    regional_items = soup.find_all('li', class_='regional__list__itm')
    for item in regional_items:
        # 直前のh3タグを取得して「シリーズ戦」グループかどうかを判定
        parent_h3 = item.find_previous('h3')
        if parent_h3 and "シリーズ戦" in parent_h3.get_text():
            continue  # シリーズ戦はスキップ

        text = item.get_text(separator=" / ", strip=True)
        clean_text = " / ".join([p.strip() for p in text.split('/') if p.strip()])
        
        if "開催日" in clean_text and "主催" in clean_text and len(clean_text) < 400:
            h = hashlib.md5(clean_text.encode('utf-8')).hexdigest()
            temp_schedule_dict[h] = f"【カップ戦】 {clean_text}"

    # 重複・部分一致排除処理
    schedule_items = []
    for h, text in temp_schedule_dict.items():
        is_subset = False
        for other_text in temp_schedule_dict.values():
            if text != other_text and text in other_text:
                is_subset = True
                break
        if not is_subset:
            schedule_items.append({"hash": h, "text": text})

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
    
    # 日本時間（JST）の取得
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst)
    current_hour = now_jst.hour
    print(f"現在時刻（日本時間）: {now_jst.strftime('%Y-%m-%d %H:%M:%S')}")

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

    # ==========================================
    # 【絶対遵守: 大量通知ストッパー（安全装置）】
    # ==========================================
    if total_changes > MAX_LIMIT:
        print(f"【安全装置発動】変更数が{total_changes}件あり上限（{MAX_LIMIT}件）を超えました。")
        print("対象変更に伴う全件検知と判定。LINE通知をスキップしてDBを最新化（既読化）します。")
        save_db(new_db)
        return

    if total_changes > 0:
        # ==========================================
        # 【夜間通知保留機能】0時〜9時未満の判定
        # ==========================================
        if 0 <= current_hour < 9:
            print(f"【夜間通知保留】現在{current_hour}時（0時〜9時未満）のため通知をスキップします。")
            print("DBの更新を行わないため、朝9時以降の実行時にまとめて通知されます。")
            return

        # 9時以降であれば通常通りLINE通知を送信し、DBを更新
        send_line_flex_carousel(added, removed)
        save_db(new_db)
        print("DBを更新しました。")
    else:
        print("スケジュールの変更はありません。")

if __name__ == "__main__":
    main()

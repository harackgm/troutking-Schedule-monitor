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
NEWS_URL = "https://www.troutking.net/news/"
DB_FILE = "schedule_db.json"
MAX_LIMIT = 10  # 【絶対遵守】一度の変更が10件を超えたら異常とみなしLINE通知をスキップ

# GitHubにアップロードされたロゴ画像の直リンクURL
LOGO_IMAGE_URL = "https://raw.githubusercontent.com/harackgm/troutking-Schedule-monitor/main/torakinlogo.png"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")

# ==========================================
# カルーセル(Flex Message)生成関数
# ==========================================
def create_change_bubble(title, old_text, new_text, link_url=TARGET_URL):
    """【変更】新旧比較用カードの生成（ロゴ画像付き）"""
    return {
        "type": "bubble",
        "hero": {
            "type": "image",
            "url": LOGO_IMAGE_URL,
            "size": "full",
            "aspectRatio": "20:3",
            "aspectMode": "cover"
        },
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
                        "uri": link_url
                    }
                }
            ]
        }
    }

def create_single_bubble(status_label, header_color, title, detail_text, link_url=TARGET_URL):
    """【新規・削除】単体データ用カードの生成（ロゴ画像付き）"""
    return {
        "type": "bubble",
        "hero": {
            "type": "image",
            "url": LOGO_IMAGE_URL,
            "size": "full",
            "aspectRatio": "20:3",
            "aspectMode": "cover"
        },
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
                        "uri": link_url
                    }
                }
            ]
        }
    }

def send_line_flex_carousel(added_list, removed_list):
    """新旧の差分を分析し、登録者全員（Broadcast）へカルーセル通知を送信する"""
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("エラー: LINE_CHANNEL_ACCESS_TOKEN が設定されていません。")
        return

    bubbles = []
    processed_removed = set()

    for add_item in added_list:
        add_parts = [p.strip() for p in add_item.split(" / ") if p.strip()]
        add_title = add_parts[0] if add_parts else ""
        add_detail = " / ".join(add_parts[1:]) if len(add_parts) > 1 else ""

        # お知らせの場合は遷移先をNEWSページヘ指定
        link_url = NEWS_URL if "【お知らせ】" in add_title else TARGET_URL

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
            bubbles.append(create_change_bubble(add_title, rem_detail, add_detail, link_url))
            processed_removed.add(matched_remove)
        else:
            bubbles.append(create_single_bubble("🟢 新規追加", "#27AE60", add_title, add_detail, link_url))

    for rem_item in removed_list:
        if rem_item not in processed_removed:
            rem_parts = [p.strip() for p in rem_item.split(" / ") if p.strip()]
            rem_title = rem_parts[0] if rem_parts else ""
            rem_detail = " / ".join(rem_parts[1:]) if len(rem_parts) > 1 else ""
            
            link_url = NEWS_URL if "【お知らせ】" in rem_title else TARGET_URL
            bubbles.append(create_single_bubble("🔴 削除/中止", "#E74C3C", rem_title, rem_detail, link_url))

    if not bubbles:
        return

    # 登録者全員へ送信するBroadcast APIエンドポイント
    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
    payload = {
        "messages": [
            {
                "type": "flex",
                "altText": "トラキンスケジュール/NEWS更新通知",
                "contents": {"type": "carousel", "contents": bubbles}
            }
        ]
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        print("LINEへの登録者全員向けブロードキャスト通知が正常に送信されました。")
    except Exception as e:
        print(f"LINE送信エラー: {e}")

# ==========================================
# スクレイピング処理（スケジュール ＋ NEWS）
# ==========================================
def get_monitored_data():
    headers = {"User-Agent": USER_AGENT}
    temp_dict = {}

    # ------------------------------------------
    # 1. スケジュールページ（本戦・カップ戦）のスクレイピング
    # ------------------------------------------
    try:
        time.sleep(2)  # サーバー負荷軽減
        response = requests.get(TARGET_URL, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        # 本戦
        main_items = soup.find_all('li', class_='main_race__cnt__list__itm__list__itm')
        for item in main_items:
            text = item.get_text(separator=" / ", strip=True)
            clean_text = " / ".join([p.strip() for p in text.split('/') if p.strip()])
            if clean_text and "大会名" not in clean_text:
                h = hashlib.md5(clean_text.encode('utf-8')).hexdigest()
                temp_dict[h] = f"【本戦】 {clean_text}"

        # カップ戦（シリーズ戦除外）
        regional_items = soup.find_all('li', class_='regional__list__itm')
        for item in regional_items:
            parent_h3 = item.find_previous('h3')
            if parent_h3 and "シリーズ戦" in parent_h3.get_text():
                continue

            text = item.get_text(separator=" / ", strip=True)
            clean_text = " / ".join([p.strip() for p in text.split('/') if p.strip()])
            
            if "シリーズ戦" in clean_text:
                continue
            
            if "開催日" in clean_text and "主催" in clean_text and len(clean_text) < 400:
                h = hashlib.md5(clean_text.encode('utf-8')).hexdigest()
                temp_dict[h] = f"【カップ戦】 {clean_text}"

    except Exception as e:
        print(f"スケジュールページの取得に失敗しました: {e}")

    # ------------------------------------------
    # 2. NEWS（お知らせ）ページのスクレイピング
    # ------------------------------------------
    try:
        time.sleep(2)  # サーバー負荷軽減
        response_news = requests.get(NEWS_URL, headers=headers, timeout=10)
        response_news.raise_for_status()
        soup_news = BeautifulSoup(response_news.content, "html.parser")

        news_items = soup_news.find_all('li', class_='m-news_list__itm')
        for item in news_items:
            date_el = item.find('span', class_='m-news_list__itm__anchor__date')
            cat_el = item.find('span', class_='m-news_list__itm__anchor__cat')
            hdg_el = item.find('h3', class_='m-news_list__itm__anchor__hdg')

            date_text = date_el.get_text(strip=True) if date_el else ""
            cat_text = cat_el.get_text(strip=True) if cat_el else ""
            hdg_text = hdg_el.get_text(strip=True) if hdg_el else ""

            if hdg_text:
                full_text = f"【お知らせ】 {hdg_text} / 日付: {date_text} / 種別: {cat_text}"
                h = hashlib.md5(full_text.encode('utf-8')).hexdigest()
                temp_dict[h] = full_text

    except Exception as e:
        print(f"NEWSページの取得に失敗しました: {e}")

    # 重複・部分一致排除処理
    schedule_items = []
    for h, text in temp_dict.items():
        is_subset = False
        for other_text in temp_dict.values():
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

    new_data = get_monitored_data()
    
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
        print("NEWS初追加等に伴う全件検知と判定。LINE通知をスキップしてDBを最新化（既読化）します。")
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

        # 9時以降であれば通常通りLINE通知（ブロードキャスト）を送信し、DBを更新
        send_line_flex_carousel(added, removed)
        save_db(new_db)
        print("DBを更新しました。")
    else:
        print("スケジュールの変更はありません。")

if __name__ == "__main__":
    main()

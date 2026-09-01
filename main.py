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
MAX_LIMIT = 5  # 【絶対遵守】一度の変更が5件を超えたら異常とみなし通知をスキップ
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# ==========================================
# 関数
# ==========================================
def get_schedule_data():
    """サイトからスケジュール情報を取得し、ハッシュ化してリストで返す"""
    headers = {"User-Agent": USER_AGENT}
    
    try:
        # 【安全対策】対象サーバーへの負荷を軽減するため2秒待機
        time.sleep(2)
        response = requests.get(TARGET_URL, headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"サイトの取得に失敗しました: {e}")
        return []

    # 取得したHTMLを解析
    soup = BeautifulSoup(response.content, "html.parser")
    schedule_items = []
    
    # 候補1: テーブル行(tr) または リスト(li) を探す
    rows = soup.find_all(["tr", "li"])
    if not rows:
        # 候補2: 見つからなければ段落(p)を探す
        rows = soup.find_all("p")
        
    for row in rows:
        text = row.get_text(separator=" ", strip=True)
        # 意味のない空白や極端に短いテキスト（10文字以下）はゴミデータとして除外
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
        print("データが取得できませんでした。サイトのHTML構造を確認し、抽出ロジックの修正が必要です。")
        return

    # 新データを辞書型に変換（ハッシュをキーにする）
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
    # 【重要: 安全装置（MAX_LIMIT制御）】
    # ==========================================
    if total_changes > MAX_LIMIT:
        print(f"【安全装置発動】変更数が{total_changes}件あり、上限（{MAX_LIMIT}件）を超えました。")
        print("初回実行、またはサイトの大規模改修とみなします。大量のLINE通知を防ぐため通知をスキップします。")
        # DBの更新のみ行う（全件既読化）
        save_db(new_db)
        print("DBのみ最新化しました。次回以降は少数の差分のみ抽出されます。")
        return

    # 擬似的なLINE通知（今回はGitHubのログ出力のみ）
    if total_changes > 0:
        print("\n--- 以下の内容をLINEに通知予定 ---")
        for text in added:
            print(f"[追加/変更] {text}")
        for text in removed:
            print(f"[削除/旧日程] {text}")
        print("------------------------------------\n")
        
        save_db(new_db)
        print("DBを更新しました。")
    else:
        print("スケジュールの変更はありません。")

if __name__ == "__main__":
    main()

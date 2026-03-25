import streamlit as st
import os
import json
import io
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# 設定網頁標題與佈局
st.set_page_config(page_title="打烊清潔照上傳系統", layout="centered")

# --- 系統設定與記憶功能 (API 綁定) ---
CONFIG_FILE = "drive_config.json"

def load_config():
    """讀取本地記憶的 API 設定"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def save_config(service_account_json_str, folder_id):
    """將 API 設定儲存到本地端產生記憶"""
    try:
        credentials_dict = json.loads(service_account_json_str)
        config = {
            "credentials": credentials_dict,
            "folder_id": folder_id.strip()
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f)
        return True
    except json.JSONDecodeError:
        return False

def delete_config():
    """刪除本地的 API 設定"""
    if os.path.exists(CONFIG_FILE):
        os.remove(CONFIG_FILE)

# --- Google Drive API 核心功能 ---
def get_drive_service(credentials_dict):
    """建立 Google Drive 連線"""
    scopes = ['https://www.googleapis.com/auth/drive']
    creds = service_account.Credentials.from_service_account_info(credentials_dict, scopes=scopes)
    return build('drive', 'v3', credentials=creds)

def create_drive_folder(service, folder_name, parent_folder_id):
    """在 Google Drive 中建立日期資料夾"""
    # 檢查是否已經有同名資料夾
    query = f"name='{folder_name}' and '{parent_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    items = results.get('files', [])
    
    if items:
        return items[0]['id'] # 已經存在，直接回傳 ID
    else:
        # 不存在，建立新資料夾
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_folder_id]
        }
        folder = service.files().create(body=file_metadata, fields='id').execute()
        return folder.get('id')

def upload_to_drive(service, file_buffer, filename, parent_folder_id, mimetype):
    """將檔案上傳至 Google Drive"""
    media = MediaIoBaseUpload(file_buffer, mimetype=mimetype, resumable=True)
    file_metadata = {
        'name': filename,
        'parents': [parent_folder_id]
    }
    service.files().create(body=file_metadata, media_body=media, fields='id').execute()

# ==========================================
# 網頁側邊欄：API 設定區
# ==========================================
with st.sidebar:
    st.header("⚙️ 系統後台設定")
    current_config = load_config()
    
    if current_config:
        st.success("✅ Google Drive API 已綁定")
        st.info("系統已記憶您的憑證。如需交接給其他人使用，請點擊下方按鈕刪除目前設定。")
        if st.button("🗑️ 刪除 API 設定", type="primary"):
            delete_config()
            st.rerun() # 重新載入網頁
    else:
        st.warning("⚠️ 尚未綁定 Google Drive")
        st.markdown("請輸入 Google Cloud 服務帳戶的 JSON 內容，以及目標資料夾 ID。")
        
        sa_json_input = st.text_area("1. 服務帳戶憑證 (JSON格式)", height=150, placeholder='{"type": "service_account", ...}')
        folder_id_input = st.text_input("2. Google Drive 目標資料夾 ID", placeholder="例如：1A2B3C4D5E6F7G8H9I")
        
        if st.button("💾 儲存並綁定"):
            if not sa_json_input or not folder_id_input:
                st.error("請填寫完整資訊！")
            else:
                success = save_config(sa_json_input, folder_id_input)
                if success:
                    st.success("設定已儲存！")
                    st.rerun()
                else:
                    st.error("JSON 格式錯誤，請檢查憑證內容！")

# ==========================================
# 網頁主畫面：員工上傳區
# ==========================================
st.title("📸 每日打烊清潔照上傳系統")

# 1. 輸入姓名欄位
uploader_name = st.text_input("請輸入您的姓名：", placeholder="例如：王小明")

# 2. 上傳區塊
st.markdown("### 🧹 外場照片 (限定 19 張)")
front_photos = st.file_uploader(
    "請選擇 19 張外場清潔照片", 
    accept_multiple_files=True, 
    key="front", 
    type=['png', 'jpg', 'jpeg']
)

st.markdown("### 🍳 內場照片 (限定 28 張)")
back_photos = st.file_uploader(
    "請選擇 28 張內場清潔照片", 
    accept_multiple_files=True, 
    key="back", 
    type=['png', 'jpg', 'jpeg']
)

# 3. 執行上傳與驗證邏輯
if st.button("確認上傳", type="primary"):
    current_config = load_config()
    
    # 檢查是否已綁定 API
    if not current_config:
        st.error("🚨 系統尚未綁定 Google Drive，請先至左側設定區完成綁定！")
    # 檢查姓名是否填寫
    elif not uploader_name.strip():
        st.warning("⚠️ 請先輸入您的姓名！")
    else:
        # 檢查上傳張數是否完全符合規定 (不刪減原本的判斷邏輯)
        if len(front_photos) != 19 or len(back_photos) != 28:
            st.error("🚨 打烊清潔照請確實拍攝到《正確張數》上傳！")
            st.info(f"📊 目前您選擇的張數：外場 {len(front_photos)} 張 / 內場 {len(back_photos)} 張")
        else:
            with st.spinner('連線至雲端並上傳中，請稍候...'):
                try:
                    # 初始化 Google Drive 服務
                    drive_service = get_drive_service(current_config["credentials"])
                    target_parent_id = current_config["folder_id"]
                    
                    # 取得當前日期作為相簿名稱
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    
                    # 在雲端建立(或取得)對應日期的資料夾
                    daily_folder_id = create_drive_folder(drive_service, today_str, target_parent_id)

                    # 處理並上傳外場照片
                    for i, photo in enumerate(front_photos):
                        ext = photo.name.split('.')[-1]
                        new_filename = f"{today_str}_{uploader_name}_外場_{i+1}.{ext}"
                        # 將照片直接從記憶體轉成 BytesIO 準備上傳
                        file_buffer = io.BytesIO(photo.getvalue())
                        upload_to_drive(drive_service, file_buffer, new_filename, daily_folder_id, photo.type)

                    # 處理並上傳內場照片
                    for i, photo in enumerate(back_photos):
                        ext = photo.name.split('.')[-1]
                        new_filename = f"{today_str}_{uploader_name}_內場_{i+1}.{ext}"
                        file_buffer = io.BytesIO(photo.getvalue())
                        upload_to_drive(drive_service, file_buffer, new_filename, daily_folder_id, photo.type)

                    st.success(f"✅ 上傳成功！共 47 張照片已重新命名並儲存至雲端硬碟「{today_str}」的相簿中。")
                
                except Exception as e:
                    st.error(f"上傳失敗，請檢查 API 設定或網路連線。錯誤訊息：{str(e)}")
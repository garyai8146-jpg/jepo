import streamlit as st
import os
import json
import io
import hashlib
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# 設定網頁標題與佈局
st.set_page_config(page_title="打烊清潔照上傳系統", layout="centered")

# --- 初始化「分批累積」與「上傳器重置」的記憶體空間 ---
if 'front_cache' not in st.session_state:
    st.session_state.front_cache = {}
if 'back_cache' not in st.session_state:
    st.session_state.back_cache = {}
if 'front_key' not in st.session_state:
    st.session_state.front_key = 0
if 'back_key' not in st.session_state:
    st.session_state.back_key = 1000

# --- 系統設定與記憶功能 (API 綁定) ---
CONFIG_FILE = "drive_config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def save_config(token_json_str, folder_id):
    try:
        credentials_dict = json.loads(token_json_str)
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
    if os.path.exists(CONFIG_FILE):
        os.remove(CONFIG_FILE)

# --- 進階 Google Drive API 功能 ---
def get_drive_service(credentials_dict):
    scopes = ['https://www.googleapis.com/auth/drive']
    creds = Credentials.from_authorized_user_info(credentials_dict, scopes=scopes)
    return build('drive', 'v3', credentials=creds)

def create_drive_folder(service, folder_name, parent_folder_id):
    query = f"name='{folder_name}' and '{parent_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    items = results.get('files', [])
    if items:
        return items[0]['id'] 
    else:
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_folder_id]
        }
        folder = service.files().create(body=file_metadata, fields='id').execute()
        return folder.get('id')

def get_existing_md5_in_folder(service, folder_id):
    hashes = set()
    page_token = None
    while True:
        query = f"'{folder_id}' in parents and trashed=false"
        results = service.files().list(
            q=query, spaces='drive', fields='nextPageToken, files(id, name, md5Checksum)', pageToken=page_token
        ).execute()
        for file in results.get('files', []):
            if 'md5Checksum' in file:
                hashes.add(file['md5Checksum'])
        page_token = results.get('nextPageToken', None)
        if not page_token:
            break
    return hashes

def calculate_local_md5(file_bytes):
    md5 = hashlib.md5()
    md5.update(file_bytes)
    return md5.hexdigest()

def threaded_upload_task(service, file_bytes, filename, mimetype, parent_folder_id, existing_hashes):
    try:
        local_hash = calculate_local_md5(file_bytes)
        if local_hash in existing_hashes:
            return {"status": "skipped", "name": filename}

        file_obj = io.BytesIO(file_bytes)
        media = MediaIoBaseUpload(file_obj, mimetype=mimetype, resumable=True)
        file_metadata = {'name': filename, 'parents': [parent_folder_id]}
        service.files().create(body=file_metadata, media_body=media, fields='id, name').execute()
        return {"status": "success", "name": filename}
    except Exception as e:
        return {"status": "error", "name": filename, "msg": str(e)}

# ==========================================
# 網頁側邊欄：API 設定區
# ==========================================
with st.sidebar:
    st.header("⚙️ 系統後台設定")
    current_config = load_config()
    
    if current_config:
        st.success("✅ Google Drive 已綁定")
        if st.button("🗑️ 刪除 API 設定", type="primary"):
            delete_config()
            st.rerun()
    else:
        st.warning("⚠️ 尚未綁定 Google Drive")
        token_json_input = st.text_area("1. 授權憑證內容")
        folder_id_input = st.text_input("2. 「總資料夾」 ID")
        if st.button("💾 儲存並綁定"):
            if save_config(token_json_input, folder_id_input):
                st.success("設定已儲存！重新整理中...")
                st.rerun()
            else:
                st.error("JSON 格式錯誤！")

# ==========================================
# 網頁主畫面：員工上傳區
# ==========================================
st.title("📸 每日打烊清潔照上傳系統")

uploader_name = st.text_input("請輸入您的姓名：", placeholder="例如：王小明")

# --- 外場上傳區 ---
st.markdown("---")
st.markdown("### 🧹 外場清潔照片 (需 19 張)")
st.caption("💡 技巧：照片選完後會自動移至下方縮圖區。若要刪除，請直接點擊照片下方的「❌ 刪除」。")

# 透過動態 key 來達成選擇後自動清空的功能
front_photos = st.file_uploader("點此選擇外場照片", accept_multiple_files=True, key=f"front_uploader_{st.session_state.front_key}", type=['png', 'jpg', 'jpeg'])

if front_photos:
    added = False
    for photo in front_photos:
        if photo.name not in st.session_state.front_cache:
            st.session_state.front_cache[photo.name] = {
                "name": photo.name, "type": photo.type, "bytes": photo.getvalue()
            }
            added = True
    if added:
        st.session_state.front_key += 1 # 改變 key，強制清空上傳框
        st.rerun()

front_count = len(st.session_state.front_cache)
st.info(f"📊 目前已累積外場照片： **{front_count} / 19** 張")

# 顯示外場縮圖與專屬刪除按鈕
if front_count > 0:
    if st.button("🗑️ 清空外場全部照片", key="clear_front_all"):
        st.session_state.front_cache = {}
        st.rerun()
    
    cols = st.columns(3)
    for i, (name, photo_data) in enumerate(list(st.session_state.front_cache.items())):
        with cols[i % 3]:
            # 取消滿版，強制設定寬度為 120，適合手機螢幕
            st.image(photo_data["bytes"], width=120)
            if st.button("❌ 刪除", key=f"del_front_{name}"):
                del st.session_state.front_cache[name]
                st.rerun()

# --- 內場上傳區 ---
st.markdown("---")
st.markdown("### 🍳 內場清潔照片 (需 28 張)")
st.caption("💡 技巧：照片選完後會自動移至下方縮圖區。若要刪除，請直接點擊照片下方的「❌ 刪除」。")

back_photos = st.file_uploader("點此選擇內場照片", accept_multiple_files=True, key=f"back_uploader_{st.session_state.back_key}", type=['png', 'jpg', 'jpeg'])

if back_photos:
    added = False
    for photo in back_photos:
        if photo.name not in st.session_state.back_cache:
            st.session_state.back_cache[photo.name] = {
                "name": photo.name, "type": photo.type, "bytes": photo.getvalue()
            }
            added = True
    if added:
        st.session_state.back_key += 1
        st.rerun()

back_count = len(st.session_state.back_cache)
st.info(f"📊 目前已累積內場照片： **{back_count} / 28** 張")

# 顯示內場縮圖與專屬刪除按鈕
if back_count > 0:
    if st.button("🗑️ 清空內場全部照片", key="clear_back_all"):
        st.session_state.back_cache = {}
        st.rerun()
        
    cols = st.columns(3)
    for i, (name, photo_data) in enumerate(list(st.session_state.back_cache.items())):
        with cols[i % 3]:
            # 取消滿版，強制設定寬度為 120
            st.image(photo_data["bytes"], width=120)
            if st.button("❌ 刪除", key=f"del_back_{name}"):
                del st.session_state.back_cache[name]
                st.rerun()

st.markdown("---")

# ==========================================
# 執行上傳邏輯
# ==========================================
if st.button("🚀 確認上傳至雲端", type="primary", use_container_width=True):
    current_config = load_config()

    if not current_config:
        st.error("🚨 系統尚未綁定 Google Drive，請先至左側設定區完成綁定！")
    elif not uploader_name.strip():
        st.warning("⚠️ 請先輸入您的姓名！")
    elif front_count == 0 and back_count == 0:
        st.warning("⚠️ 請至少累積外場或內場照片後再進行上傳！")
    else:
        front_invalid = (front_count > 0 and front_count != 19)
        back_invalid = (back_count > 0 and back_count != 28)

        if front_invalid or back_invalid:
            st.error("🚨 打烊清潔照請確實拍攝到《正確張數》上傳！")
        else:
            upload_spinner = st.spinner('🔐 正在連線雲端並檢查重複照片中...')
            with upload_spinner:
                try:
                    drive_service = get_drive_service(current_config["credentials"])
                    target_parent_id = current_config["folder_id"]
                    
                    now = datetime.now()
                    roc_year = now.year - 1911
                    date_str_folder = f"{roc_year}/{now.strftime('%m/%d')}"
                    date_str_file = f"{roc_year}-{now.strftime('%m-%d')}"

                    upload_tasks = []
                    MAX_THREADS = 5 
                    
                    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
                        # 處理外場
                        if front_count == 19:
                            front_folder_name = f"{date_str_folder}外場清潔-{uploader_name}"
                            front_folder_id = create_drive_folder(drive_service, front_folder_name, target_parent_id)
                            existing_hashes_front = get_existing_md5_in_folder(drive_service, front_folder_id)
                            
                            for i, (name, photo_data) in enumerate(st.session_state.front_cache.items()):
                                ext = name.split('.')[-1]
                                new_filename = f"{date_str_file}_{uploader_name}_外場清潔_{i+1}.{ext}"
                                upload_tasks.append(
                                    executor.submit(
                                        threaded_upload_task, drive_service, photo_data["bytes"], new_filename, photo_data["type"], front_folder_id, existing_hashes_front
                                    )
                                )

                        # 處理內場
                        if back_count == 28:
                            back_folder_name = f"{date_str_folder}內場清潔-{uploader_name}"
                            back_folder_id = create_drive_folder(drive_service, back_folder_name, target_parent_id)
                            existing_hashes_back = get_existing_md5_in_folder(drive_service, back_folder_id)
                            
                            for i, (name, photo_data) in enumerate(st.session_state.back_cache.items()):
                                ext = name.split('.')[-1]
                                new_filename = f"{date_str_file}_{uploader_name}_內場清潔_{i+1}.{ext}"
                                upload_tasks.append(
                                    executor.submit(
                                        threaded_upload_task, drive_service, photo_data["bytes"], new_filename, photo_data["type"], back_folder_id, existing_hashes_back
                                    )
                                )

                        progress_bar = st.progress(0, text="開始並行上傳...")
                        success_count = 0
                        skip_count = 0
                        total_tasks = len(upload_tasks)
                        
                        for i, future in enumerate(as_completed(upload_tasks)):
                            result = future.result()
                            if result["status"] == "success": success_count += 1
                            elif result["status"] == "skipped": skip_count += 1
                            else: st.error(f"檔案上傳失敗: {result['name']}, 錯誤: {result['msg']}")
                            
                            progress_bar.progress((i + 1) / total_tasks, text=f"上傳進度: {i+1}/{total_tasks} 🚀")

                    # 上傳完成，清空記憶體
                    st.session_state.front_cache = {}
                    st.session_state.back_cache = {}

                    if success_count == 0 and skip_count > 0:
                        st.warning(f"🔔 雲端硬碟已存在全部相片。跳過重複照片 {skip_count} 張。")
                    elif success_count > 0:
                        msg = f"✅ 上傳成功！共上傳 {success_count} 張照片至雲端硬碟。"
                        if skip_count > 0: msg += f" (自動跳過重複照片 {skip_count} 張)"
                        st.success(msg)
                
                except Exception as e:
                    st.error(f"連線伺服器失敗，請確認網路。錯誤訊息：{str(e)}")

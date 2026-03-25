import streamlit as st
import os
import json
import io
import hashlib
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
# ⚠️ 這裡改引入 Credentials 了，請確保你是按照之前的步驟產生的 token.json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# 設定網頁標題與佈局
st.set_page_config(page_title="打烊清潔照上傳系統", layout="centered")

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
    """在 Google Drive 中建立相簿資料夾 (或回傳已存在的 ID)"""
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
    """掃描目標資料夾中所有檔案的 MD5 雜湊值"""
    hashes = set()
    page_token = None
    while True:
        # 查詢語句：在该文件夹下，且未被删除的所有文件
        query = f"'{folder_id}' in parents and trashed=false"
        results = service.files().list(
            q=query,
            spaces='drive',
            fields='nextPageToken, files(id, name, md5Checksum)',
            pageToken=page_token
        ).execute()
        
        for file in results.get('files', []):
            if 'md5Checksum' in file:
                hashes.add(file['md5Checksum'])
        
        page_token = results.get('nextPageToken', None)
        if not page_token:
            break
    return hashes

def calculate_local_md5(file_stream):
    """計算本地上傳檔案的 MD5 雜湊值 (不用讀取全部內容到記憶體)"""
    md5 = hashlib.md5()
    file_stream.seek(0) # 確保從頭讀取
    # 分塊讀取防止大檔案撐爆記憶體
    for chunk in iter(lambda: file_stream.read(4096), b""):
        md5.update(chunk)
    file_stream.seek(0) # 讀完後將指標歸零，供後續上傳使用
    return md5.hexdigest()

def threaded_upload_task(service, file_obj, filename, parent_folder_id, existing_hashes):
    """單一檔案上傳任務 (包含重複檢查與重試機制)"""
    try:
        # 1. 計算本地檔案 MD5 指紋
        local_hash = calculate_local_md5(file_obj)
        
        # 2. 比對雲端指紋，若重複則跳過
        if local_hash in existing_hashes:
            return {"status": "skipped", "name": filename}

        # 3. 執行上傳
        file_obj.seek(0) # 再次確保指標從頭讀取內容
        media = MediaIoBaseUpload(file_obj, mimetype=file_obj.type, resumable=True)
        file_metadata = {
            'name': filename,
            'parents': [parent_folder_id]
        }
        # 使用 resumable 上傳大檔案較穩定
        service.files().create(body=file_metadata, media_body=media, fields='id, name').execute()
        return {"status": "success", "name": filename}
        
    except Exception as e:
        return {"status": "error", "name": filename, "msg": str(e)}

# ==========================================
# 網頁側邊欄：API 設定區 (不變)
# ==========================================
with st.sidebar:
    st.header("⚙️ 系統後台設定")
    current_config = load_config()
    
    if current_config:
        st.success("✅ Google Drive API 已綁定")
        st.info("如需交接用不同帳號，請點擊下方按鈕刪除。")
        if st.button("🗑️ 刪除 API 設定", type="primary"):
            delete_config()
            st.rerun()
    else:
        st.warning("⚠️ 尚未綁定 Google Drive")
        st.markdown("請貼上真實帳號授權的 `token.json` 內容，以及**總資料夾 ID**。")
        token_json_input = st.text_area("1. 授權憑證內容", height=150, placeholder='{"token": "...", "refresh_token": "..."}')
        folder_id_input = st.text_input("2. 「總資料夾」 ID", placeholder="例如：1n-wWYu0COFuMd0CczPdv...")
        
        if st.button("💾 儲存並綁定"):
            if not token_json_input or not folder_id_input:
                st.error("請填寫完整資訊！")
            else:
                success = save_config(token_json_input, folder_id_input)
                if success:
                    st.success("設定已儲存！重新整理中...")
                    st.rerun()
                else:
                    st.error("JSON 格式錯誤，請檢查憑證內容！")

# ==========================================
# 網頁主畫面：員工上傳區
# ==========================================
st.title("📸 每日打烊清潔照上傳系統")

uploader_name = st.text_input("請輸入您的姓名：", placeholder="例如：王小明")

# --- 外場上傳區 (縮圖功能在裡面) ---
st.markdown("---")
st.markdown("### 🧹 外場清潔照片 (限定 19 張)")
st.caption("💡手機「長按」照片可多選；電腦「Ctrl」鍵多選。重複檔案將自動跳過。")
front_photos = st.file_uploader(
    "請選擇 19 張外場清潔照片", 
    accept_multiple_files=True, 
    key="front", 
    type=['png', 'jpg', 'jpeg']
)

# 新增：外場縮圖顯示
if front_photos:
    st.write(f"📊 已選擇 **{len(front_photos)}** 張照片：")
    cols = st.columns(6) # 一行顯示 6 張縮圖
    for i, photo in enumerate(front_photos):
        with cols[i % 6]:
            st.image(photo, use_container_width=True) # use_column_width 改為 use_container_width

# --- 內場上傳區 (縮圖功能在裡面) ---
st.markdown("---")
st.markdown("### 🍳 內場清潔照片 (限定 28 張)")
st.caption("💡手機「長按」照片可多選；電腦「Ctrl」鍵多選。重複檔案將自動跳過。")
back_photos = st.file_uploader(
    "請選擇 28 張內場清潔照片", 
    accept_multiple_files=True, 
    key="back", 
    type=['png', 'jpg', 'jpeg']
)

# 新增：內場縮圖顯示
if back_photos:
    st.write(f"📊 已選擇 **{len(back_photos)}** 張照片：")
    cols = st.columns(6)
    for i, photo in enumerate(back_photos):
        with cols[i % 6]:
            st.image(photo, use_container_width=True)

st.markdown("---")
if st.button("🚀 確認上傳照片", type="primary", use_container_width=True):
    current_config = load_config()
    front_count = len(front_photos)
    back_count = len(back_photos)

    if not current_config:
        st.error("🚨 系統尚未綁定 Google Drive，請先至左側設定區完成綁定！")
    elif not uploader_name.strip():
        st.warning("⚠️ 請先輸入您的姓名！")
    elif front_count == 0 and back_count == 0:
        st.warning("⚠️ 請至少選擇外場或內場照片進行上傳！")
    else:
        # 判定張數限制，未滿或超出都擋掉
        front_invalid = (front_count > 0 and front_count != 19)
        back_invalid = (back_count > 0 and back_count != 28)

        if front_invalid or back_invalid:
            st.error("🚨 打烊清潔照請確實拍攝到《正確張數》上傳！")
            if front_invalid: st.info(f"📊 外場需 19 張，目前選擇：{front_count} 張")
            if back_invalid: st.info(f"📊 內場需 28 張，目前選擇：{back_count} 張")
        else:
            upload_spinner = st.spinner('🔐 正在連線雲端並處理重複照片檢查...')
            with upload_spinner:
                try:
                    drive_service = get_drive_service(current_config["credentials"])
                    target_parent_id = current_config["folder_id"]
                    
                    now = datetime.now()
                    roc_year = now.year - 1911
                    date_str_folder = f"{roc_year}/{now.strftime('%m/%d')}"
                    date_str_file = f"{roc_year}-{now.strftime('%m-%d')}"

                    upload_tasks = []
                    # 💡 設定並行數量。Streamlit Cloud 環境建議設為 4 或 5，太高可能會被 Google 擋流量。
                    MAX_THREADS = 5 
                    
                    # 準備執行序處理池
                    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
                        
                        # --- 處理外場照片並行任務 ---
                        if front_count == 19:
                            front_folder_name = f"{date_str_folder}外場清潔-{uploader_name}"
                            front_folder_id = create_drive_folder(drive_service, front_folder_name, target_parent_id)
                            # 先掃描一次資料夾，取得已存在的檔案指紋
                            st.write(f"🔍 掃描【外場相簿】重複照片中...")
                            existing_hashes_front = get_existing_md5_in_folder(drive_service, front_folder_id)
                            
                            for i, photo in enumerate(front_photos):
                                ext = photo.name.split('.')[-1]
                                new_filename = f"{date_str_file}_{uploader_name}_外場清潔_{i+1}.{ext}"
                                # 將單一檔案的上傳任務丟進處理池
                                upload_tasks.append(
                                    executor.submit(
                                        threaded_upload_task, 
                                        drive_service, 
                                        io.BytesIO(photo.getvalue()), # ⚠️ IO 流需要複製一份傳遞給線程
                                        new_filename, 
                                        front_folder_id, 
                                        existing_hashes_front
                                    )
                                )

                        # --- 處理內場照片並行任務 ---
                        if back_count == 28:
                            back_folder_name = f"{date_str_folder}內場清潔-{uploader_name}"
                            back_folder_id = create_drive_folder(drive_service, back_folder_name, target_parent_id)
                            # 先掃描一次資料夾，取得已存在的檔案指紋
                            st.write(f"🔍 掃描【內場相簿】重複照片中...")
                            existing_hashes_back = get_existing_md5_in_folder(drive_service, back_folder_id)
                            
                            for i, photo in enumerate(back_photos):
                                ext = photo.name.split('.')[-1]
                                new_filename = f"{date_str_file}_{uploader_name}_內場清潔_{i+1}.{ext}"
                                # 將單一檔案的上傳任務丟進處理池
                                upload_tasks.append(
                                    executor.submit(
                                        threaded_upload_task, 
                                        drive_service, 
                                        io.BytesIO(photo.getvalue()), # IO 流需要複製一份
                                        new_filename, 
                                        back_folder_id, 
                                        existing_hashes_back
                                    )
                                )

                        # --- 監視任務完成進度 ---
                        progress_bar = st.progress(0, text="開始並行上傳...")
                        success_count = 0
                        skip_count = 0
                        total_tasks = len(upload_tasks)
                        
                        # 迴圈接收完成的任務
                        for i, future in enumerate(as_completed(upload_tasks)):
                            result = future.result()
                            if result["status"] == "success":
                                success_count += 1
                            elif result["status"] == "skipped":
                                skip_count += 1
                            elif result["status"] == "error":
                                st.error(f"檔案上傳失敗: {result['name']}, 錯誤: {result['msg']}")
                            
                            # 更新進度條
                            progress_bar.progress((i + 1) / total_tasks, text=f"並行上傳進度: {i+1}/{total_tasks} 🚀")

                    # 上傳完成後的最終報告
                    if success_count == 0 and skip_count > 0:
                        st.warning(f"🔔 雲端硬碟已存在全部相片。跳過重複照片 {skip_count} 張。")
                    elif success_count > 0:
                        msg = f"✅ 上傳成功！共上傳 {success_count} 張照片至雲端硬碟。"
                        if skip_count > 0:
                            msg += f" (同時自動跳過重複照片 {skip_count} 張)"
                        st.success(msg)
                
                except Exception as e:
                    st.error(f"連線伺服器失敗，請確認網路或認證檔。錯誤訊息：{str(e)}")

# 打烊清潔照上傳系統｜Store Closing Photo Uploader

> 將門市打烊後的清潔照片整理、壓縮與去重，再依工作區域批次上傳至 Google Drive 的 Streamlit 工作台。

## 為什麼做這個專案

門市清潔回報通常需要反覆選取多張照片、手動建立資料夾、確認照片有沒有重複上傳。這個工具把流程整合成單一畫面，讓店員專注於回報，減少整理檔案的重複操作。

**工作流程：** 選取前場／後場照片 → 分批累積 → 圖片壓縮 → MD5 比對 → 建立或尋找 Drive 資料夾 → 並行上傳 → 顯示上傳／略過結果。

## 主要功能與技術決策

- **批量圖片處理：** 使用 Pillow 等比例縮圖並輸出 JPEG，減少雲端傳輸與儲存成本。
- **重複檔案檢查：** 比對本地圖片 MD5 與 Google Drive 回傳的 `md5Checksum`，降低重複上傳機率。
- **並行上傳：** 使用 `ThreadPoolExecutor` 與 Google Drive API 處理多張圖片。
- **分區與暫存：** Streamlit Session State 管理前場、後場與分批選檔。
- **資料夾自動整理：** 查詢或建立指定父資料夾下的回報目錄。

## 技術棧

Python · Streamlit · Pillow · Google Drive API v3 · Google OAuth 2.0 · concurrent.futures

## 本機執行

1. 安裝 Python 3 與本專案相依套件。
2. 執行 `pip install -r requirements.txt`。
3. 執行 `streamlit run app.py`。
4. 在應用程式介面提供自己 Google 帳戶授權產生的 OAuth 使用者憑證與目標 Drive 資料夾 ID。

> **資料安全提醒：** 現有程式會在本機 `drive_config.json` 保存 OAuth 使用者憑證。此檔可能含有敏感權杖，請勿提交至 Git、分享給他人或放在公用電腦。此專案屬門市工作流程工具原型，正式多人部署前應改用安全的憑證儲存與權限管理。

## 面試時可以談的工程問題

如何在節省圖片儲存空間的同時保持可辨識度？Google Drive API 的延遲與多張照片上傳如何處理？如何界定「相同檔案」與「視覺相似但檔案不同」？

## 限制

MD5 是位元內容的重複檢查，不是圖片相似度辨識；不同壓縮或重新拍攝的照片不一定能被判定為同一張。上傳是否成功仍取決於使用者的 Google Drive 授權、配額及網路。

# jepo｜打烊清潔照，不用再一張一張整理

門市打烊後要上傳不少清潔照片。照片常常分不同區域，傳錯資料夾或重複上傳都很麻煩。這個工具就是想把「選照片 → 分類 → 壓縮 → 檢查重複 → 上傳」變成比較順手的一次操作。

**[回到面試作品集](https://github.com/garyai8146-jpg/Yihop_LineBOT/blob/main/PORTFOLIO.md)**

## 做了哪些事

- 前場與後場的照片可以分開累積，不用一次選完。
- 使用 Pillow 壓縮圖片，降低上傳量。
- 用檔案內容 MD5 和 Google Drive 的檢查碼比對，減少完全相同照片的重複上傳。
- 自動尋找或建立對應 Google Drive 資料夾。
- 透過 ThreadPoolExecutor 並行上傳，顯示成功與略過結果。

## 執行

```powershell
python -m pip install -r requirements.txt
streamlit run app.py
```

使用時需要你自己授權的 Google Drive 使用者憑證與目標資料夾 ID。現有原型可能在本機 `drive_config.json` 保存 OAuth 資料，**不要上傳這個檔案，也不要把正式帳號放到公開測試環境**。

## 這個小工具的難點

「一模一樣的檔案」和「看起來是一樣的照片」不是同一回事。MD5 只能比對檔案內容；重新拍照或重新壓縮之後，檢查碼就可能不同。

另一個問題是批次上傳的失敗回報：並行處理雖然能加快速度，但每張照片是否成功、要不要重試，都需要清楚記錄。

這是實際流程的輔助原型，仍需要依帳號權限、Google Drive API 配額與網路環境驗證。公開程式碼不含門市的清潔照或真實憑證。

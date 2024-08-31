# Audio Transcription and Translation

此專案用於對音檔進行分割、過濾、轉錄和翻譯，並將結果保存為文本檔案。

## 環境設置

1. 請確保您的系統已安裝 Python 3。
2. 安裝必要的套件：

```bash
pip install -r requirements.txt
```

3. 在項目根目錄下創建的 `.env` 檔案，並添加您的 OpenAI API 密鑰：

```bash
OPENAI_API_KEY=your_openai_api_key
```

## 目錄結構

```bash
.
├── m4a/                 # 存放原始音檔的目錄
├── text/                # 存放轉錄和翻譯結果的目錄
├── script.py            # 主程式碼檔案
├── .env                 # 環境變數檔案 (包含 API 密鑰)
└── README.md            # 本說明文件

```

## 使用方式

1. 將您需要處理的 .m4a 音檔放置在 m4a 目錄下。

2. 編輯 script.py 的 file_paths 和 output_file 變數，指定要處理的音檔名稱和輸出結果的檔案名稱。

```python
if __name__ == "__main__":
    file_paths = [
        os.path.join(AUDIO_DIR, "XXXXX.m4a"),
    ]
    output_file = os.path.join(TEXT_DIR, "XXXXX.txt")
```

3. 執行程式碼：

```bash
python script.py
```

4. 轉錄與翻譯結果將被保存至 text 目錄中的指定檔案。

## 功能

- 音檔過濾：對音檔進行高通、低通濾波和增益控制，以保留語音清晰度並去除噪音。
- 音檔分割：將音檔分割成小於 15MB 的片段，並導出為 .mp3 格式。
- 音檔轉錄：使用 OpenAI 的 Whisper 模型將音檔轉錄為文本。
- 文本翻譯：使用 GPT 將轉錄結果翻譯為繁體中文（臺灣）。

## 錯誤處理

程式在處理音檔的各個階段都有錯誤處理機制，當發生錯誤時，會在終端顯示錯誤訊息。

## 注意事項

- 在 .env 檔案中務必妥善保護您的 API 密鑰，不要將它包含在版本控制中。
- 請確保音檔的大小和格式符合您的需求，否則可能會影響處理結果。

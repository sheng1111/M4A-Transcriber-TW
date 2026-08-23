# VoiceScribe

VoiceScribe 是以 OpenAI API 為核心的音檔轉錄與臺灣繁體中文翻譯工具，提供命令列與 Tkinter 圖形介面。v2.4.1 著重內容忠實度、可續跑、錯誤可見性、低記憶體音訊處理與清楚的結果分類。

目前版本：`2.4.1`

## 主要功能

- 預設使用 OpenAI `gpt-transcribe` 進行檔案轉錄。
- 預設使用 `gpt-5.6-luna` 與 Responses API 翻譯，固定 `reasoning.effort="none"`。
- 將原始轉錄切成帶 ID 的文字段落，要求模型逐段回傳；缺段、空白實質段落或錯誤 ID 不會寫成最終成品。
- 保留原始轉錄、各片段結果與處理 manifest，失敗後可從成功步驟繼續。
- 使用 FFmpeg 直接切割為 16kHz、單聲道、96kbps MP3，不把整個長音檔載入 Python 記憶體。
- 支援 M4A、MP3、WAV、FLAC、AAC、MP4、MPEG、WebM。
- 每個來源音檔使用獨立結果資料夾，避免原始資料、翻譯與處理狀態混在一起。

OpenAI 官方文件建議一般錄音檔從 `gpt-transcribe` 開始；它支援錄音背景、關鍵字和多語言提示。`gpt-5.6-luna` 支援 Responses API、Structured Outputs 與 `none` reasoning effort。

- [OpenAI File Transcription](https://developers.openai.com/api/docs/guides/speech-to-text)
- [GPT Transcribe model](https://developers.openai.com/api/docs/models/gpt-transcribe)
- [GPT-5.6 Luna model](https://developers.openai.com/api/docs/models/gpt-5.6-luna)

## 系統需求

- Python 3.8 或更新版本
- FFmpeg 與 FFprobe
- OpenAI API Key

安裝 Python 套件：

```bash
python -m pip install -r requirements.txt -U
```

安裝 FFmpeg：

```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt update
sudo apt install ffmpeg
```

Windows 請安裝 FFmpeg 並將 `ffmpeg`、`ffprobe` 加入 PATH。

## API Key

複製範本後填入自己的 Key：

```bash
cp .env.example .env
```

```dotenv
OPENAI_API_KEY=your_openai_api_key_here
```

`.env` 只保留在本機，不會進入 Git。若 Key 曾經提交到 Git 歷史，停止追蹤並不能撤銷該 Key，請到 OpenAI 平台撤銷舊 Key 並建立新 Key。

## 圖形介面

```bash
python gui_app.py
```

新版工作台包含：

- 左側工作佇列：加入檔案、加入資料夾、移除與清除。
- 右側設定：API Key、輸出路徑、模型、語言、術語、背景與效能參數。
- 結果預覽：依音檔瀏覽 `final.txt`，並可開啟完整結果資料夾。
- 活動記錄與固定進度列：明確顯示轉錄、翻譯、快取、失敗與停止狀態。

忠實翻譯核心提示詞受保護。GUI 只能追加錄音背景、正確術語和格式偏好，不能取消逐段完整輸出或改成摘要。

## 命令列

直接帶入一個或多個檔案，不必修改 `app.py`：

```bash
python app.py speech/meeting.m4a speech/interview.mp3
```

處理整個資料夾：

```bash
python app.py ./recordings --output-dir ./text
```

加入語言、術語與錄音背景：

```bash
python app.py speech/meeting.m4a \
  --language zh \
  --language en \
  --keyword OpenAI \
  --keyword "Responses API" \
  --context "中英文混合的技術會議"
```

查看所有選項：

```bash
python app.py --help
```

未指定輸入時會遞迴掃描 `speech/`。預設輸出根目錄為 `text/`。

## 結果結構

每個音檔使用獨立資料夾：

```text
text/
└── meeting/
    ├── final.txt
    ├── raw.txt
    ├── manifest.json
    └── chunks/
        ├── a0000.raw.txt
        ├── a0001.raw.txt
        ├── s00001.zh-TW.txt
        └── s00002.zh-TW.txt
```

- `raw.txt`：依音訊片段順序合併的原始轉錄。
- `final.txt`：通過段落完整性驗證的臺灣繁體中文成品。
- `manifest.json`：來源雜湊、設定雜湊、模型、狀態與錯誤。
- `chunks/`：可續跑的音訊片段原始文字與翻譯文字。

如果不同來源具有相同檔名，第二個來源會自動加入來源雜湊後綴，避免覆寫。

## 可續跑與失敗行為

- 來源 SHA-256 與 ASR 設定相同時，可以重用原始轉錄。
- 只有翻譯設定改變時，會保留原始轉錄並重做翻譯。
- 逾時、HTTP 429 與伺服器錯誤最多重試三次；認證和參數錯誤立即失敗。
- 最終成品以原子替換寫入。失敗、取消或空白輸出不會覆蓋先前成功的 `final.txt`。
- 暫存音訊無論成功或失敗都會清除。

## 模型與提示參數

預設模型：

| 用途 | 預設值 |
| --- | --- |
| 語音轉錄 | `gpt-transcribe` |
| 繁中翻譯 | `gpt-5.6-luna` |
| Reasoning effort | `none` |
| Text verbosity | `high` |

可選轉錄模型：

- `gpt-transcribe`
- `gpt-4o-transcribe`
- `gpt-4o-mini-transcribe`
- `whisper-1`

可選翻譯模型：

- `gpt-5.6-luna`
- `gpt-5.6-terra`
- `gpt-5.6-sol`

對 `gpt-transcribe`，程式使用 `prompt`、`keywords`、`languages`。其他轉錄模型會依能力改用單一 `language` 與提示文字。

## 開發與驗證

語法檢查：

```bash
python -m py_compile app.py gui_app.py
```

測試：

```bash
pytest -q
```

測試使用模擬 OpenAI 回應，不會產生付費 API 呼叫。

## v2.4.1 更新內容

- 將轉錄模型的空白回應視為無語音片段，不再因錄音尾端靜音導致整個作業失敗。
- 空白片段亦可正確續跑，但所有片段都無內容時仍會回報錯誤。

## v2.4.0 更新內容

- CLI 改為直接接收檔案與資料夾，移除硬編碼檔名與個人提示詞。
- ASR 預設升級為 `gpt-transcribe`。
- 翻譯升級為 `gpt-5.6-luna`、Responses API、Structured Outputs 與 none reasoning。
- 新增逐段完整性契約，避免模型偷偷摘要或省略內容。
- 新增每檔結果分類、來源與設定雜湊、部分續跑及原子寫入。
- 重做 GUI 工作台與執行緒事件傳遞。
- 將音訊切割移至 FFmpeg 子程序，降低記憶體使用量。
- `.env` 停止 Git 追蹤並加入安全範本。

## License

本專案採用 MIT License，詳見 [LICENSE](LICENSE)。

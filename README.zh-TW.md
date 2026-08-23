# VoiceScribe

[English](readme.md) | [繁體中文](README.zh-TW.md)

VoiceScribe 是以 OpenAI API 為核心的多語言音檔轉錄與忠實翻譯工具，提供命令列與 Tkinter 圖形介面。翻譯預設輸出臺灣繁體中文（`zh-TW`），也可由使用者指定任何有效的 BCP 47 目標語言代碼。

目前版本：`2.4.3`

## 主要功能

- 預設使用 OpenAI `gpt-transcribe` 進行音檔轉錄。
- 預設使用 `gpt-5.6-luna` 與 Responses API 翻譯，固定 `reasoning.effort="none"`。
- 支援 `zh-TW`、`en`、`ja`、`ko`、`pt-BR` 等可設定的翻譯目標語言。
- 提供僅轉錄模式，可略過翻譯及其 API 成本。
- 以逐段輸出契約驗證結果，缺少 ID、省略內容或格式錯誤的回應不會寫成最終成品。
- 來源與設定未改變時，可續用已完成的轉錄與翻譯結果。
- 使用 FFmpeg 低記憶體切割長錄音，不將整個檔案載入 Python 記憶體。
- 支援 M4A、MP3、WAV、FLAC、AAC、MP4、MPEG、WebM。
- 每個來源音檔都有獨立結果資料夾，保存原始文字、最終文字、片段快取與處理 manifest。

## 系統需求

- Python 3.10 或更新版本
- PATH 中可使用 FFmpeg 與 FFprobe
- OpenAI API Key

安裝 Python 套件：

```bash
python -m pip install -r requirements.txt -U
```

在 macOS 安裝 FFmpeg：

```bash
brew install ffmpeg
```

在 Ubuntu 或 Debian 安裝 FFmpeg：

```bash
sudo apt update
sudo apt install ffmpeg
```

Windows 請安裝 FFmpeg，並將 `ffmpeg`、`ffprobe` 加入 PATH。

## API Key

複製環境範本後填入 Key：

```bash
cp .env.example .env
```

```dotenv
OPENAI_API_KEY=your_openai_api_key_here
```

`.env` 只保留在本機且已由 Git 忽略。若 Key 曾經提交到版本歷史，請到 OpenAI 平台撤銷並建立新 Key。

## 圖形介面

```bash
python gui_app.py
```

工作台包含：

- 可加入單一檔案或遞迴加入資料夾的批次佇列。
- API Key、輸出路徑、模型、語言、術語、背景與效能設定。
- 可編輯的目標語言選單，內建常用 BCP 47 語言代碼。
- 「僅轉錄，不翻譯 / Transcript only」選項。
- 最終結果預覽、活動記錄、進度顯示、取消與中斷續跑。

忠實翻譯核心提示詞受保護。錄音背景、正確術語與格式偏好只會作為低優先資料，不能要求摘要或省略來源內容。

## 命令列

處理一個或多個檔案：

```bash
python app.py speech/meeting.m4a speech/interview.mp3
```

遞迴處理整個資料夾：

```bash
python app.py ./recordings --output-dir ./text
```

翻譯成日文：

```bash
python app.py speech/meeting.m4a --target-language ja
```

加入音檔語言提示、術語與錄音背景：

```bash
python app.py speech/meeting.m4a \
  --language zh \
  --language en \
  --keyword OpenAI \
  --keyword "Responses API" \
  --context "中英文混合的技術會議"
```

只產生逐字稿並略過翻譯：

```bash
python app.py speech/meeting.m4a --transcript-only
```

`--language` 是可重複使用的音檔內容語言提示；`--target-language` 是單一翻譯目標語言，預設為 `zh-TW`。

使用 `python app.py --help` 查看所有選項。未指定輸入時，VoiceScribe 會遞迴掃描 `speech/`；預設輸出根目錄為 `text/`。

## 結果結構

每個來源使用獨立資料夾：

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
- `final.txt`：通過驗證的翻譯；在僅轉錄模式中則為逐字稿。
- `manifest.json`：記錄來源雜湊、設定、模式、語言、模型、狀態與錯誤。
- `chunks/`：保存可續跑的音訊片段原始文字與翻譯文字。

不同來源若檔名相同但內容不同，VoiceScribe 會加入來源雜湊後綴，避免覆寫既有作業。

## 可續跑與失敗行為

- 來源與 ASR 設定相同時會重用原始轉錄。
- 只有翻譯設定改變時，會保留原始轉錄並僅重做翻譯。
- 改變目標語言會使翻譯快取失效，但不會重新轉錄音訊。
- 在翻譯與僅轉錄模式之間切換時，不會誤用不相容的 `final.txt`。
- 逾時、HTTP 429 與伺服器錯誤預設最多重試三次。
- 最終成品以原子替換寫入；失敗、取消、不完整或空白翻譯不會覆蓋先前成功結果。
- 暫存音訊無論成功或失敗都會清除。

## 模型與語言選項

| 用途 | 預設值 |
| --- | --- |
| 語音轉錄 | `gpt-transcribe` |
| 文字翻譯 | `gpt-5.6-luna` |
| 目標語言 | `zh-TW` |
| Reasoning effort | `none` |
| Text verbosity | `high` |

支援的轉錄模型：

- `gpt-transcribe`
- `gpt-4o-transcribe`
- `gpt-4o-mini-transcribe`
- `whisper-1`

支援的翻譯模型：

- `gpt-5.6-luna`
- `gpt-5.6-terra`
- `gpt-5.6-sol`

GUI 提供 `zh-TW`、`zh-CN`、`en`、`ja`、`ko`、`es`、`fr`、`de`、`it`、`pt-BR` 等常用目標語言。欄位仍可編輯，因此也接受其他有效的 BCP 47 語言代碼。

對 `gpt-transcribe`，VoiceScribe 會傳送 `prompt`、`keywords` 與 `languages`。其他轉錄模型則依介面能力使用單一 `language` 與提示文字。

## 開發與驗證

檢查 Python 語法：

```bash
python -m py_compile app.py gui_app.py
```

執行測試：

```bash
pytest -q
```

測試使用模擬 OpenAI 回應，不會產生付費 API 呼叫。

## 版本紀錄

### v2.4.3

- CLI 與 GUI 新增僅轉錄模式。
- 英文 README 與 CLI 說明改為主要入口，方便國際使用者。
- 新增完整繁中對照 README。
- 新增模式切換的快取安全測試。

### v2.4.2

- CLI 與 GUI 新增可設定的目標語言，預設維持 `zh-TW`。
- 目標語言會寫入提示詞、快取雜湊、片段檔名與 manifest。
- 核心模型提示改為英文，方便維護多語言行為。

### v2.4.1

- 將空白 ASR 回應視為靜音片段，但仍會拒絕整段皆無語音的錄音。

### v2.4.0

- 新增檔案與資料夾 CLI 輸入、可續跑處理、原子輸出、結構化翻譯驗證與低記憶體 FFmpeg 分段。

## License

本專案採用 [MIT License](LICENSE)。

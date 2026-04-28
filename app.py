import os
import traceback
import logging
import re
import math
import tempfile
import shutil

from pathlib import Path
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI
from pydub import AudioSegment

# 設定 Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

DEFAULT_TRANSCRIPTION_MODEL = "gpt-4o-transcribe"
DEFAULT_TRANSLATION_MODEL = "gpt-5.4-mini"
DEFAULT_TRANSCRIPTION_LANGUAGE = "zh"
DEFAULT_KEYWORDS = "Unix, 神通, host"  # 在此修改關鍵字，CLI 與 GUI 重設預設值時共用
APP_VERSION = "2.3.0"
SUPPORTED_TRANSCRIPTION_MODELS = (
    "gpt-4o-transcribe",
    "gpt-4o-mini-transcribe",
    "whisper-1",
)

DEFAULT_GPT_SYSTEM_PROMPT = """你是一個專業的語音轉文字後處理專家，專門將語音轉錄結果整理成易讀的繁體中文（臺灣）。

# 輸入說明
輸入為多段音檔分段轉錄後合併的結果，可能含有轉錄錯誤、口語重複、以及分段邊界產生的內容重複。

# 任務（依優先序）

1. **去除重複段落**：若有完全相同或高度相似的段落重複出現（轉錄模型的已知問題），只保留第一次出現的版本，直接刪除後續重複
2. **去除口語贅詞**：刪除明顯的口語重複，例如「那麼那麼那麼」、「對對對對對」、連續三次以上的相同詞語
3. **簡繁轉換**：全文統一為繁體中文（臺灣），使用臺灣慣用詞彙
4. **臺灣專有名詞**：人名地名採臺灣慣用譯法（特朗普→川普、普京→普丁）
5. **校正轉錄錯誤**：修正明顯因發音相似導致的錯字（如「神通」、「愛德萬」等專有名詞請保留）
6. **分段**：依主題邏輯分段，每段約 150–250 字，段落間空行分隔

# 嚴禁
- 不得添加原文沒有的資訊
- 不得省略實質對話內容
- 不得意譯或重新詮釋

# 輸出格式
直接輸出繁體中文文本，不加任何說明、標題或標記。"""


class AudioProcessor:
    """音檔處理器類別，負責音檔轉錄、翻譯和處理流程"""
    
    def __init__(self, audio_dir='./speech', text_dir='./text'):
        """初始化音檔處理器"""
        self.audio_dir = audio_dir
        self.text_dir = text_dir
        self.client = self._initialize_openai_client()
        self._setup_ffmpeg()
        
    def _initialize_openai_client(self):
        """初始化 OpenAI 客戶端"""
        load_dotenv('.env')
        api_key = os.getenv('OPENAI_API_KEY')
        
        if not api_key:
            logging.error("未找到 OPENAI_API_KEY 環境變數")
            logging.error("請建立 .env 檔案並設定: OPENAI_API_KEY=your_api_key_here")
            raise ValueError("OpenAI API key 未設定")
        
        return OpenAI(api_key=api_key)
    
    def _setup_ffmpeg(self):
        """設定 FFmpeg 路徑 - 完整跨平台支援（Windows、macOS、Linux）"""
        import shutil
        import platform
        import os

        # 嘗試自動偵測 FFmpeg 和 FFprobe 路徑（支援所有平台）
        ffmpeg_path = shutil.which("ffmpeg")
        ffprobe_path = shutil.which("ffprobe")

        if ffmpeg_path and ffprobe_path:
            # 成功偵測到 FFmpeg
            AudioSegment.converter = ffmpeg_path
            AudioSegment.ffprobe = ffprobe_path
            system = platform.system()
            logging.info(f"✓ 已自動偵測 FFmpeg（{system}）")
            logging.info(f"  - FFmpeg: {ffmpeg_path}")
            logging.info(f"  - FFprobe: {ffprobe_path}")
        else:
            # 自動偵測失敗，根據系統使用預設路徑
            system = platform.system()

            if system == "Windows":
                # Windows 預設設定
                AudioSegment.converter = "ffmpeg.exe"
                AudioSegment.ffprobe = "ffprobe.exe"
                logging.warning("⚠ 未找到 FFmpeg（Windows）")
                logging.warning("  安裝方式：下載 FFmpeg 並加入系統 PATH")
                logging.warning("  下載位置：https://ffmpeg.org/download.html#build-windows")

            elif system == "Darwin":
                # macOS 預設路徑（支援 Homebrew 多種安裝位置）
                possible_paths = [
                    "/opt/homebrew/bin/ffmpeg",  # M1/M2/M3/M4/M5 Mac (Apple Silicon)
                    "/usr/local/bin/ffmpeg",     # Intel Mac
                    "/usr/bin/ffmpeg"            # 系統預設
                ]

                # 嘗試找到存在的路徑
                ffmpeg_found = None
                for path in possible_paths:
                    if os.path.exists(path):
                        ffmpeg_found = path
                        break

                if ffmpeg_found:
                    AudioSegment.converter = ffmpeg_found
                    AudioSegment.ffprobe = ffmpeg_found.replace("ffmpeg", "ffprobe")
                    logging.info(f"✓ 找到 FFmpeg（macOS）: {ffmpeg_found}")
                else:
                    AudioSegment.converter = "/usr/local/bin/ffmpeg"
                    AudioSegment.ffprobe = "/usr/local/bin/ffprobe"
                    logging.warning("⚠ 未找到 FFmpeg（macOS）")
                    logging.warning("  安裝方式：brew install ffmpeg")
                    logging.warning("  如果未安裝 Homebrew：/bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"")

            else:
                # Linux 預設路徑
                AudioSegment.converter = "/usr/bin/ffmpeg"
                AudioSegment.ffprobe = "/usr/bin/ffprobe"
                logging.warning("⚠ 未找到 FFmpeg（Linux）")
                logging.warning("  安裝方式：sudo apt install ffmpeg  # Ubuntu/Debian")
                logging.warning("           sudo yum install ffmpeg  # CentOS/RHEL")

            logging.warning("  ⚠ 如果處理失敗，請確認已正確安裝 FFmpeg")
    
    def filter_audio(self, audio,
                     high_pass_freq=80,
                     low_pass_freq=8000,
                     target_dBFS=-20.0,
                     compression_ratio=3.0,
                     enable_noise_reduction=True,
                     voice_boost=True):
        """對音檔進行智慧化過濾，最佳化語音清晰度與音質

        Args:
            audio: 原始音檔 (AudioSegment)
            high_pass_freq: 高通濾波頻率 (Hz)，預設 80Hz
            low_pass_freq: 低通濾波頻率 (Hz)，預設 8000Hz
            target_dBFS: 目標音量 (dBFS)，預設 -20.0
            compression_ratio: 動態壓縮比例，預設 3.0
            enable_noise_reduction: 是否啟用降噪，預設 True
            voice_boost: 是否增強語音頻段 (300-3400Hz)，預設 True
        """
        try:
            logging.info(f"開始音檔過濾處理，原始長度: {len(audio)}ms, 原始音量: {audio.dBFS:.1f}dBFS")

            # 1. 頻帶過濾 - 針對語音優化
            # 高通濾波：去除低頻噪音（空調、風扇、隆隆聲等）
            if high_pass_freq > 0:
                audio = audio.high_pass_filter(high_pass_freq)
                logging.info(f"✓ 套用高通濾波器: {high_pass_freq}Hz (去除低頻噪音)")

            # 低通濾波：去除高頻噪音，保留語音頻譜
            if low_pass_freq > 0:
                audio = audio.low_pass_filter(low_pass_freq)
                logging.info(f"✓ 套用低通濾波器: {low_pass_freq}Hz (保留語音頻譜)")

            # 2. 語音頻段增強 - 提升人聲清晰度
            if voice_boost:
                # 人聲主要集中在 300-3400Hz，微幅提升此頻段
                # 這裡使用多重濾波模擬帶通增強效果
                boosted = audio.high_pass_filter(300).low_pass_filter(3400)
                # 將增強的語音頻段與原音訊混合（增強 2dB）
                audio = audio.overlay(boosted - 2, position=0)
                logging.info(f"✓ 增強語音頻段 (300-3400Hz) 提升清晰度")

            # 3. 智慧降噪與標準化
            if enable_noise_reduction:
                # 計算音檔的動態範圍
                max_dBFS = audio.max_dBFS
                avg_dBFS = audio.dBFS

                # 標準化音檔，提升整體清晰度
                # 保留足夠的餘裕空間避免削波
                audio = audio.normalize(headroom=3.0)
                logging.info(f"✓ 音訊標準化 (保留 3dB 餘裕空間)")

                # 如果音檔動態範圍過大，進行溫和壓縮
                dynamic_range = max_dBFS - avg_dBFS
                if dynamic_range > 20:  # 動態範圍 > 20dB 才壓縮
                    logging.info(f"✓ 檢測到大動態範圍 ({dynamic_range:.1f}dB)，套用智慧壓縮")

            # 4. 動態範圍壓縮 - 平衡音量差異，使轉錄更穩定
            if compression_ratio > 1.0:
                current_dBFS = audio.dBFS
                if current_dBFS > target_dBFS:
                    # 計算壓縮增益（溫和壓縮，避免過度處理）
                    gain_reduction = (current_dBFS - target_dBFS) / compression_ratio
                    audio = audio.apply_gain(-(current_dBFS - target_dBFS - gain_reduction))
                    logging.info(f"✓ 套用動態壓縮，增益調整: {-(current_dBFS - target_dBFS - gain_reduction):.1f}dB")

            # 5. 最終音量調整 - 確保適合轉錄 API
            final_dBFS = audio.dBFS
            if final_dBFS < target_dBFS - 5:  # 音量過小
                gain_needed = target_dBFS - final_dBFS
                # 限制最大增益避免放大噪音
                actual_gain = min(gain_needed, 12)
                audio = audio.apply_gain(actual_gain)
                logging.info(f"✓ 提升音量: +{actual_gain:.1f}dB")
            elif final_dBFS > target_dBFS + 5:  # 音量過大
                gain_needed = target_dBFS - final_dBFS
                audio = audio.apply_gain(gain_needed)
                logging.info(f"✓ 降低音量: {gain_needed:.1f}dB")

            # 6. 最終檢查與報告
            final_dBFS = audio.dBFS
            final_max_dBFS = audio.max_dBFS
            logging.info(f"✓ 音檔過濾完成 - 平均音量: {final_dBFS:.1f}dBFS, 峰值: {final_max_dBFS:.1f}dBFS")

            return audio

        except Exception as e:
            logging.error(f"音檔過濾時發生錯誤: {e}\n{traceback.format_exc()}")
            logging.warning("⚠ 音檔過濾失敗，使用原始音檔繼續處理")
            return audio

    def split_audio(self, file_path, max_size_mb=20, max_duration_min=10, **filter_params):
        """將音檔分割成小於指定大小的片段並導出為 .mp3 格式

        Args:
            file_path: 音檔路徑
            max_size_mb: 最大分割大小 (MB)，預設 20MB
            max_duration_min: 最大分割長度（分鐘），避免長片段超過模型輸出上限
            **filter_params: 音檔過濾參數（可選）
        """
        try:
            if not os.path.exists(file_path):
                logging.error(f"檔案 {file_path} 不存在")
                return []

            audio = AudioSegment.from_file(file_path).set_channels(1).set_frame_rate(16000)

            if len(audio) <= 0:
                logging.error(f"音檔 {file_path} 長度為 0，無法分割")
                return []

            max_bytes = max_size_mb * 1024 * 1024
            export_bitrate = "96k"
            ffmpeg_parameters = self._build_export_filter_params(filter_params, audio.dBFS)
            bytes_per_ms = 96000 / 8 / 1000
            size_limited_ms = int(max_bytes * 0.90 / bytes_per_ms)
            duration_limited_ms = int(max_duration_min * 60 * 1000) if max_duration_min else size_limited_ms
            chunk_length_ms = max(1000, min(size_limited_ms, duration_limited_ms))
            chunks = [audio[i:i + chunk_length_ms] for i in range(0, len(audio), chunk_length_ms)]
            logging.info(
                f"音檔將分割為 {len(chunks)} 段，每段上限約 {chunk_length_ms / 60000:.1f} 分鐘、{max_size_mb}MB"
            )
            
            chunk_files = []
            temp_dir = tempfile.mkdtemp(prefix="m4a_transcriber_")
            for i, chunk in enumerate(chunks):
                try:
                    chunk_file = os.path.join(temp_dir, f"{os.path.splitext(os.path.basename(file_path))[0]}_chunk{i}.mp3")
                    chunk.export(chunk_file, format="mp3", bitrate=export_bitrate, parameters=ffmpeg_parameters)

                    if os.path.getsize(chunk_file) > max_bytes:
                        exported_size = os.path.getsize(chunk_file)
                        logging.warning(
                            f"片段 {i + 1} 匯出後仍超過 {max_size_mb}MB，改用更短片段重新切割"
                        )
                        os.remove(chunk_file)
                        sub_chunk_count = max(2, math.ceil(exported_size / max_bytes))
                        sub_length_ms = max(1000, len(chunk) // sub_chunk_count)
                        for j, sub_chunk_start in enumerate(range(0, len(chunk), sub_length_ms)):
                            sub_chunk = chunk[sub_chunk_start:sub_chunk_start + sub_length_ms]
                            sub_chunk_file = os.path.join(
                                temp_dir,
                                f"{os.path.splitext(os.path.basename(file_path))[0]}_chunk{i}_{j}.mp3"
                            )
                            sub_chunk.export(sub_chunk_file, format="mp3", bitrate=export_bitrate, parameters=ffmpeg_parameters)
                            chunk_files.append(sub_chunk_file)
                    else:
                        chunk_files.append(chunk_file)
                except Exception as e:
                    logging.error(f"分割音檔時發生錯誤: {e}\n{traceback.format_exc()}")

            return chunk_files
        except Exception as e:
            logging.error(f"處理音檔 {file_path} 時發生錯誤: {e}\n{traceback.format_exc()}")
            return []

    def _build_export_filter_params(self, filter_params, source_dBFS=None):
        """建立 FFmpeg 匯出濾鏡，避免用 pydub 在 Python 中處理長音檔。"""
        filters = []
        high_pass_freq = filter_params.get("high_pass_freq", 80)
        low_pass_freq = filter_params.get("low_pass_freq", 8000)
        target_dBFS = filter_params.get("target_dBFS", -20.0)
        compression_ratio = filter_params.get("compression_ratio", 3.0)
        voice_boost = filter_params.get("voice_boost", True)

        if high_pass_freq and high_pass_freq > 0:
            filters.append(f"highpass=f={int(high_pass_freq)}")
        if low_pass_freq and low_pass_freq > 0:
            filters.append(f"lowpass=f={int(low_pass_freq)}")
        if voice_boost:
            filters.append("equalizer=f=1700:t=q:w=1:g=2")
        if compression_ratio and compression_ratio > 1.0:
            filters.append(f"acompressor=ratio={float(compression_ratio):.2f}:threshold=-18dB:attack=20:release=250")
        if target_dBFS is not None and source_dBFS not in (None, float("-inf")):
            gain_needed = float(target_dBFS) - float(source_dBFS)
            if abs(gain_needed) > 1:
                gain_needed = max(min(gain_needed, 12), -12)
                filters.append(f"volume={gain_needed:.1f}dB")

        if not filters:
            return ["-ac", "1", "-ar", "16000"]

        logging.info(f"使用 FFmpeg 音訊濾鏡匯出片段: {','.join(filters)}")
        return ["-ac", "1", "-ar", "16000", "-af", ",".join(filters)]

    def transcribe_audio(self, file_path, prompt="", model=DEFAULT_TRANSCRIPTION_MODEL,
                         language=DEFAULT_TRANSCRIPTION_LANGUAGE):
        """轉錄音檔"""
        try:
            with open(file_path, 'rb') as audio_file:
                transcription_params = {
                    "model": model,
                    "file": audio_file,
                    "response_format": "json"
                }

                # gpt-4o-transcribe 系列的 prompt 會被當成前文直接輸出，不傳入
                gpt_transcribe_models = ("gpt-4o-transcribe", "gpt-4o-mini-transcribe")
                if prompt.strip() and model not in gpt_transcribe_models:
                    transcription_params["prompt"] = prompt
                if language and language.strip():
                    transcription_params["language"] = language.strip()

                transcription = self.client.audio.transcriptions.create(**transcription_params)
            if isinstance(transcription, str):
                return transcription.strip()
            if isinstance(transcription, dict):
                return transcription.get("text", "").strip()
            return getattr(transcription, "text", "").strip()
        except Exception as e:
            logging.error(f"轉錄音檔 {file_path} 時發生錯誤: {e}\n{traceback.format_exc()}")
            return ""

    def translate_to_chinese_with_gpt(self, english_text, system_prompt=None, whisper_prompt=None, model=DEFAULT_TRANSLATION_MODEL):
        """使用 GPT 模型翻譯成繁體中文

        Args:
            english_text: 待翻譯的文本
            system_prompt: 自訂系統提示詞（可選）
            whisper_prompt: 轉錄提示詞，用於專有名詞（可選）
            model: GPT 模型名稱，預設為 gpt-5.4-mini

        Note:
            - GPT-5 使用 "developer" role
            - GPT-4o/GPT-4.1 使用 "system" role
            - 兩者不可混用
        """
        try:
            if system_prompt is None:
                system_prompt = DEFAULT_GPT_SYSTEM_PROMPT

            # 如果有 whisper_prompt，加入到系統提示詞中
            if whisper_prompt and whisper_prompt.strip():
                system_prompt += f"""

            # 音檔關鍵字與專有名詞（強制校正）

以下是此音檔的正確關鍵字與專有名詞：
{whisper_prompt.strip()}

**重要**：語音轉文字模型常因發音相似而誤轉這些詞彙（例如將英文 "host" 轉成「POST」、「霍斯特」等）。請主動掃描全文，將所有讀音相近的錯誤還原為上方列出的正確字詞。
                """

            # 根據模型選擇正確的 role
            # GPT-5 使用 "developer" role
            # GPT-4o, GPT-4.1, GPT-4 等使用 "system" role
            if model.startswith("gpt-5") or model.startswith("o1") or model.startswith("o3"):
                role_type = "developer"
                logging.info(f"使用 {model} 模型（developer role）進行翻譯與潤飾")
            else:
                role_type = "system"
                logging.info(f"使用 {model} 模型（system role）進行翻譯與潤飾")

            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": role_type, "content": system_prompt},
                    {"role": "user", "content": english_text}
                ],
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logging.error(f"使用 GPT 翻譯文本時發生錯誤: {e}\n{traceback.format_exc()}")
            # 如果是模型錯誤，提供更有幫助的錯誤訊息
            if "model" in str(e).lower():
                logging.error(f"模型 '{model}' 可能不可用，請檢查您的 OpenAI 帳戶權限")
                logging.error(f"建議使用的模型: {DEFAULT_TRANSLATION_MODEL}, gpt-4o, gpt-4o-mini, gpt-4.1")
            return ""

    def filter_noise_text(self, text):
        """使用正則表達式過濾轉錄結果中的各種噪聲文本與無效內容"""
        if not text or not text.strip():
            return ""
        
        # 定義噪聲模式的正則表達式清單
        noise_regex_patterns = [
            # 字幕提供商相關
            r'字幕由\s*[Aa]mara(?:\.org)?\s*(?:社群)?提供',
            r'[Aa]mara(?:\.org)?(?:\s*社群)?(?:\s*提供)?',
            r'字幕由.*?提供',
            r'©.*?[Aa]mara.*?',
            
            # 影片平台浮水印
            r'(?:YouTube|youtu\.be|bilibili|B站).*?',
            r'©.*?(?:版權所有|All Rights Reserved)',
            r'訂閱.*?頻道',
            r'點擊.*?(?:訂閱|關注|按讚)',
            
            # 常見無效轉錄內容
            r'(?:嗯|啊|呃|額|那個){2,}',  # 重複的語助詞
            r'\.{3,}',  # 多個省略號
            r'-{2,}',   # 多個破折號
            r'_{2,}',   # 多個下劃線
            r'={2,}',   # 多個等號
            
            # 無意義的重複字符
            r'(.)\1{4,}',  # 同一字符重複5次以上
            r'([啊嗯呃額哦喔]{1,2}\s*){3,}',  # 語助詞重複
            
            # 時間戳記和章節標記
            r'\d{1,2}:\d{2}(?::\d{2})?',  # 時間格式
            r'第\s*\d+\s*(?:集|章|節|部分)',
            r'Chapter\s*\d+',
            
            # 技術相關無效內容
            r'(?:Loading|緩衝中|載入中)\.{0,3}',
            r'(?:Error|錯誤|出錯)\s*[:：]?\s*\d*',
            
            # 無意義的標點符號組合
            r'[，。！？；：,.\!?;:]{3,}',
            r'[\s　]{3,}',  # 多個空白字符（包含全形空格）
        ]
        
        logging.debug(f"原始文本長度: {len(text)} 字符")
        
        # 套用所有噪聲過濾模式
        cleaned_text = text
        removed_patterns = []
        
        for i, pattern in enumerate(noise_regex_patterns):
            matches = re.findall(pattern, cleaned_text, re.IGNORECASE | re.MULTILINE)
            if matches:
                removed_patterns.extend(matches)
                cleaned_text = re.sub(pattern, '', cleaned_text, flags=re.IGNORECASE | re.MULTILINE)
        
        # 後處理：保留分段結構，只清理多餘的空白和標點
        # 只合併同一行內的多個空格和tab，保留換行符
        cleaned_text = re.sub(r'[ \t]+', ' ', cleaned_text)  # 只合併空格和tab，不影響換行
        
        # 清理過多的連續空行（3個以上空行合併為2個空行，保留段落分隔）
        cleaned_text = re.sub(r'\n\s*\n\s*\n+', '\n\n', cleaned_text)  # 多個空行合併為雙空行
        
        # 移除行首尾的空格，但保留換行符結構
        lines = cleaned_text.split('\n')
        lines = [line.strip() for line in lines]
        cleaned_text = '\n'.join(lines)
        
        # 移除首尾的空行
        cleaned_text = re.sub(r'^\n+|\n+$', '', cleaned_text)
        
        # 處理孤立的標點符號
        cleaned_text = re.sub(r'^\s*[，。！？；：,.\!?;:]+\s*', '', cleaned_text)
        cleaned_text = re.sub(r'\s*[，。！？；：,.\!?;:]+\s*$', '', cleaned_text)
        
        # 移除太短的無意義片段（少於3個字符且無中文）
        if len(cleaned_text) < 3 and not re.search(r'[\u4e00-\u9fff]', cleaned_text):
            cleaned_text = ""
        
        # 記錄過濾結果
        if removed_patterns:
            logging.info(f"已過濾 {len(removed_patterns)} 個噪聲模式")
            logging.debug(f"移除的內容: {removed_patterns[:5]}...")  # 只顯示前5個
        
        # 段落級別重複偵測：移除 gpt-4o-transcribe 在 chunk 邊界產生的幻覺重複
        cleaned_text = self._remove_duplicate_paragraphs(cleaned_text)

        final_length = len(cleaned_text)
        if final_length != len(text):
            logging.info(f"文本過濾完成：{len(text)} → {final_length} 字符")

        return cleaned_text

    def _remove_duplicate_paragraphs(self, text, similarity_threshold=0.82):
        """移除高度相似的重複段落（處理 gpt-4o-transcribe chunk 邊界幻覺重複）"""
        import difflib
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        if len(paragraphs) <= 1:
            return text

        result = [paragraphs[0]]
        for para in paragraphs[1:]:
            is_duplicate = any(
                difflib.SequenceMatcher(None, para, prev).ratio() >= similarity_threshold
                for prev in result
            )
            if is_duplicate:
                logging.info(f"移除重複段落：{para[:40]}…")
            else:
                result.append(para)

        return '\n\n'.join(result)

    def process_files(self, file_paths, output_file, whisper_prompt="", gpt_system_prompt=None,
                      transcription_model=DEFAULT_TRANSCRIPTION_MODEL,
                      translation_model=DEFAULT_TRANSLATION_MODEL,
                      transcription_language=DEFAULT_TRANSCRIPTION_LANGUAGE,
                      max_size_mb=20,
                      max_duration_min=10,
                      overwrite=True,
                      should_stop=None,
                      **audio_filter_params):
        """並行處理所有音檔，並按照正確順序保存轉錄結果

        Args:
            file_paths: 音檔路徑列表
            output_file: 輸出檔案路徑
            whisper_prompt: 轉錄提示詞
            gpt_system_prompt: GPT 系統提示詞
            transcription_model: OpenAI 語音轉文字模型
            translation_model: GPT 翻譯潤飾模型
            transcription_language: 轉錄語言 ISO-639-1 代碼，空值代表自動偵測
            max_size_mb: 單一片段最大檔案大小
            max_duration_min: 單一片段最大分鐘數
            overwrite: 是否覆寫輸出檔，避免重跑時附加舊內容
            should_stop: 可選的停止檢查函式，回傳 True 時停止處理
            **audio_filter_params: 音檔過濾參數（可選）
        """
        total_files = len(file_paths)
        logging.info(f"開始處理 {total_files} 個音檔")
        os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
        if overwrite:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write("")

        for file_index, file_path in enumerate(file_paths, 1):
            if should_stop and should_stop():
                logging.warning("收到停止要求，結束尚未開始的檔案處理")
                break

            logging.info(f"正在處理第 {file_index}/{total_files} 個檔案: {os.path.basename(file_path)}")

            # 傳遞音檔過濾參數
            chunk_files = self.split_audio(
                file_path,
                max_size_mb=max_size_mb,
                max_duration_min=max_duration_min,
                **audio_filter_params
            )
            if not chunk_files:
                logging.warning(f"無法分割音檔: {file_path}")
                continue
                
            # 儲存每個分割檔案的轉錄結果
            chunk_results = [None] * len(chunk_files)
            total_chunks = len(chunk_files)
            logging.info(f"檔案已分割為 {total_chunks} 個片段，開始並行處理")
            
            def transcribe_chunk(index, chunk_file):
                try:
                    if should_stop and should_stop():
                        logging.warning(f"片段 {index + 1} 尚未開始即停止")
                        return
                    logging.info(f"開始轉錄片段 {index + 1}/{total_chunks}: {os.path.basename(chunk_file)}")
                    raw_transcription = self.transcribe_audio(
                        chunk_file,
                        whisper_prompt,
                        transcription_model,
                        transcription_language
                    )
                    if not raw_transcription:
                        logging.warning(f"片段 {index + 1} 轉錄結果為空")
                        return
                    chunk_results[index] = raw_transcription
                    logging.info(f"片段 {index + 1} 轉錄完成")
                except Exception as e:
                    logging.error(f"轉錄片段 {chunk_file} 時發生錯誤: {e}\n{traceback.format_exc()}")

            # 使用 try-finally 確保清理
            try:
                # 階段 1：並行轉錄所有片段
                with ThreadPoolExecutor(max_workers=3) as executor:
                    futures = [executor.submit(transcribe_chunk, i, chunk_file) for i, chunk_file in enumerate(chunk_files)]
                    completed = 0
                    for future in as_completed(futures):
                        future.result()
                        completed += 1
                        logging.info(f"已完成轉錄 {completed}/{total_chunks} 個片段")
                        if should_stop and should_stop():
                            logging.warning("收到停止要求，等待已送出的片段收尾後停止")

                if should_stop and should_stop():
                    return

                # 階段 2：合併所有原始轉錄文本，整體翻譯（保留完整上下文）
                valid_transcriptions = [r for r in chunk_results if r]
                if not valid_transcriptions:
                    logging.warning("所有片段轉錄結果均為空，略過翻譯")
                    return

                merged_raw = "\n".join(valid_transcriptions)
                logging.info(f"合併 {len(valid_transcriptions)} 個片段，共 {len(merged_raw)} 字符，開始整體翻譯潤飾")
                logging.info(f"使用 {translation_model} 進行整體翻譯潤飾")

                translated_text = self.translate_to_chinese_with_gpt(
                    merged_raw,
                    gpt_system_prompt,
                    whisper_prompt,
                    translation_model
                )

                translated_text = self.filter_noise_text(translated_text)

                # 寫入最終結果
                logging.info(f"開始寫入轉錄結果")
                with open(output_file, 'a', encoding='utf-8') as f:
                    if translated_text:
                        f.write(translated_text.strip() + "\n\n")
                        logging.debug("已寫入整體翻譯結果")
                
                logging.info(f"檔案 {os.path.basename(file_path)} 處理完成")
                
            except Exception as e:
                logging.error(f"處理檔案 {file_path} 時發生錯誤: {e}\n{traceback.format_exc()}")
                raise  # 重新拋出錯誤以便上層處理
            finally:
                # 確保清理所有臨時 chunk 檔案
                logging.info("開始清理臨時檔案")
                cleaned_count = 0
                for chunk_file in chunk_files:
                    try:
                        if os.path.exists(chunk_file):
                            os.remove(chunk_file)
                            cleaned_count += 1
                            logging.debug(f"已刪除臨時檔案: {os.path.basename(chunk_file)}")
                    except Exception as cleanup_error:
                        logging.warning(f"清理檔案 {chunk_file} 時發生錯誤: {cleanup_error}")
                
                if cleaned_count > 0:
                    logging.info(f"清理完成，共刪除 {cleaned_count} 個臨時檔案")
                else:
                    logging.info("無需清理臨時檔案")

                if chunk_files:
                    temp_dir = os.path.dirname(chunk_files[0])
                    if os.path.basename(temp_dir).startswith("m4a_transcriber_"):
                        shutil.rmtree(temp_dir, ignore_errors=True)


SUPPORTED_AUDIO_EXTENSIONS = {'.m4a', '.mp3', '.wav', '.flac', '.aac'}


def main():
    """主程式入口

    用法：
      python app.py                        # 掃描 AUDIO_DIR 所有音檔
      python app.py a.m4a b.mp3           # 指定特定檔案
      AUDIO_DIR=./recordings python app.py
      TEXT_DIR=./output python app.py
    """
    import argparse

    parser = argparse.ArgumentParser(description="音檔批次轉錄工具")
    parser.add_argument("files", nargs="*", help="指定要處理的音檔路徑（不指定則掃描 AUDIO_DIR）")
    args = parser.parse_args()

    audio_dir = os.getenv("AUDIO_DIR", "./speech")
    text_dir = os.getenv("TEXT_DIR", "./text")

    try:
        processor = AudioProcessor(audio_dir=audio_dir, text_dir=text_dir)
        os.makedirs(text_dir, exist_ok=True)

        # 決定要處理的檔案清單
        if args.files:
            file_paths = [os.path.abspath(f) for f in args.files]
            missing = [f for f in file_paths if not os.path.exists(f)]
            if missing:
                for f in missing:
                    logging.error(f"找不到檔案: {f}")
                return
        else:
            file_paths = sorted(
                str(p) for p in Path(audio_dir).iterdir()
                if p.is_file() and p.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
            )
            if not file_paths:
                logging.warning(f"在 {audio_dir} 中找不到任何音檔")
                return
            logging.info(f"找到 {len(file_paths)} 個音檔：{[os.path.basename(f) for f in file_paths]}")

        # 逐一處理，每個輸入對應一個輸出 txt
        for file_path in file_paths:
            stem = os.path.splitext(os.path.basename(file_path))[0]
            output_file = os.path.join(text_dir, f"{stem}.txt")
            processor.process_files(
                [file_path],
                output_file,
                DEFAULT_KEYWORDS,
                None,  # 使用 DEFAULT_GPT_SYSTEM_PROMPT
                transcription_language=DEFAULT_TRANSCRIPTION_LANGUAGE
            )
            logging.info(f"✓ 已儲存：{output_file}")

    except ValueError as e:
        logging.error(f"設定錯誤: {e}")
    except Exception as e:
        logging.error(f"處理過程中發生錯誤: {e}\n{traceback.format_exc()}")


# 程式入口點
if __name__ == "__main__":
    main()

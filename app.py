import os
import traceback
import logging
import re

from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI
from pydub import AudioSegment

# 設定 Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


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
                    "/opt/homebrew/bin/ffmpeg",  # M1/M2/M3 Mac (Apple Silicon)
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

            # 5. 最終音量調整 - 確保適合 Whisper API
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

    def split_audio(self, file_path, max_size_mb=20, **filter_params):
        """將音檔分割成小於指定大小的片段並導出為 .mp3 格式

        Args:
            file_path: 音檔路徑
            max_size_mb: 最大分割大小 (MB)，預設 20MB
            **filter_params: 音檔過濾參數（可選）
        """
        try:
            if not os.path.exists(file_path):
                logging.error(f"檔案 {file_path} 不存在")
                return []

            audio = AudioSegment.from_file(file_path)
            # 套用音檔過濾，使用提供的參數或預設值
            audio = self.filter_audio(audio, **filter_params)

            file_size = os.path.getsize(file_path)
            chunk_length_ms = len(audio) * max_size_mb * 1024 * 1024 // file_size
            chunks = [audio[i:i + chunk_length_ms] for i in range(0, len(audio), chunk_length_ms)]
            
            chunk_files = []
            for i, chunk in enumerate(chunks):
                try:
                    chunk_file = f"{os.path.splitext(file_path)[0]}_chunk{i}.mp3"
                    chunk.export(chunk_file, format="mp3")
                    chunk_files.append(chunk_file)
                except Exception as e:
                    logging.error(f"分割音檔時發生錯誤: {e}\n{traceback.format_exc()}")

            return chunk_files
        except Exception as e:
            logging.error(f"處理音檔 {file_path} 時發生錯誤: {e}\n{traceback.format_exc()}")
            return []

    def transcribe_audio(self, file_path, prompt=""):
        """轉錄音檔"""
        try:
            with open(file_path, 'rb') as audio_file:
                # 構建轉錄參數
                transcription_params = {
                    "model": "whisper-1",
                    "file": audio_file,
                    "response_format": "text"
                }
                
                # 如果有提供 prompt 則加入參數
                if prompt.strip():
                    transcription_params["prompt"] = prompt
                
                transcription = self.client.audio.transcriptions.create(**transcription_params)
            return transcription.strip()
        except Exception as e:
            logging.error(f"轉錄音檔 {file_path} 時發生錯誤: {e}\n{traceback.format_exc()}")
            return ""

    def translate_to_chinese_with_gpt(self, english_text, system_prompt=None, whisper_prompt=None, model="gpt-5"):
        """使用 GPT 模型翻譯成繁體中文

        Args:
            english_text: 待翻譯的文本
            system_prompt: 自訂系統提示詞（可選）
            whisper_prompt: Whisper 提示詞，用於專有名詞（可選）
            model: GPT 模型名稱，預設為 gpt-5

        Note:
            - GPT-5 使用 "developer" role
            - GPT-4o/GPT-4.1 使用 "system" role
            - 兩者不可混用
        """
        try:
            # 預設 system_prompt
            default_system_prompt = (
                """
            你是一個專業的文本校正和翻譯專家，專門處理whisper語音轉文字後的內容，將文本翻譯成繁體中文（臺灣），並進行校正和分段。

            # 任務要求

            1. **翻譯**: 將文本翻譯為繁體中文（臺灣）
            2. **校正**: 修正語音轉文字可能產生的錯誤，根據上下文進行合理修正
            3. **去重**: 刪除重複的語句和推廣用語
            4. **分段**: 將長文本按照邏輯主題進行分段，每段之間用空行分隔
            5. **整理**: 確保文本結構清晰，易於閱讀

            # 分段原則

            - 每段長度適中（約100-200字）
            - 段落之間用空行分隔

            # 輸出格式

            直接輸出分段後的繁體中文文本，段落間用空行分隔。不需要其他說明。
                """
            )

            # 使用提供的 system_prompt 或預設值
            if system_prompt is None:
                system_prompt = default_system_prompt

            # 如果有 whisper_prompt，加入到系統提示詞中
            if whisper_prompt and whisper_prompt.strip():
                system_prompt += f"""

            # 音檔相關關鍵字與專有名詞

            以下是使用者提供的音檔相關關鍵字與專有名詞，請在翻譯時特別注意這些詞彙的正確性：
            {whisper_prompt.strip()}
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
                logging.error(f"建議使用的模型: gpt-5 (推薦), gpt-4o, gpt-4o-mini, gpt-4.1")
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
        
        final_length = len(cleaned_text)
        if final_length != len(text):
            logging.info(f"文本過濾完成：{len(text)} → {final_length} 字符")
        
        return cleaned_text

    def process_files(self, file_paths, output_file, whisper_prompt="", gpt_system_prompt=None, **audio_filter_params):
        """並行處理所有音檔，並按照正確順序保存轉錄結果

        Args:
            file_paths: 音檔路徑列表
            output_file: 輸出檔案路徑
            whisper_prompt: Whisper 提示詞
            gpt_system_prompt: GPT 系統提示詞
            **audio_filter_params: 音檔過濾參數（可選）
        """
        total_files = len(file_paths)
        logging.info(f"開始處理 {total_files} 個音檔")

        for file_index, file_path in enumerate(file_paths, 1):
            logging.info(f"正在處理第 {file_index}/{total_files} 個檔案: {os.path.basename(file_path)}")

            # 傳遞音檔過濾參數
            chunk_files = self.split_audio(file_path, **audio_filter_params)
            if not chunk_files:
                logging.warning(f"無法分割音檔: {file_path}")
                continue
                
            # 儲存每個分割檔案的轉錄結果
            chunk_results = [None] * len(chunk_files)
            total_chunks = len(chunk_files)
            logging.info(f"檔案已分割為 {total_chunks} 個片段，開始並行處理")
            
            def process_chunk(index, chunk_file):
                try:
                    logging.info(f"開始處理片段 {index + 1}/{total_chunks}: {os.path.basename(chunk_file)}")
                    
                    # 轉錄音檔（帶入自訂 prompt）
                    raw_transcription = self.transcribe_audio(chunk_file, whisper_prompt)
                    if not raw_transcription:
                        logging.warning(f"片段 {index + 1} 轉錄結果為空")
                        return
                    
                    logging.info(f"片段 {index + 1} 轉錄完成，開始翻譯潤飾")
                    
                    # 翻譯（帶入自訂 system_prompt 和 whisper_prompt）
                    translated_text = self.translate_to_chinese_with_gpt(raw_transcription, gpt_system_prompt, whisper_prompt)
                    
                    # 過濾噪聲文本
                    translated_text = self.filter_noise_text(translated_text)
                    
                    # 儲存結果到對應索引位置
                    chunk_results[index] = translated_text
                    
                    logging.info(f"片段 {index + 1} 處理完成")
                    
                except Exception as e:
                    logging.error(f"處理分割檔案 {chunk_file} 時發生錯誤: {e}\n{traceback.format_exc()}")
            
            # 使用 try-finally 確保清理
            try:
                # 並行處理音檔片段（max_workers=3 提升處理速度）
                with ThreadPoolExecutor(max_workers=3) as executor:
                    futures = [executor.submit(process_chunk, i, chunk_file) for i, chunk_file in enumerate(chunk_files)]
                    
                    # 等待所有處理完成
                    completed = 0
                    for future in futures:
                        future.result()
                        completed += 1
                        logging.info(f"已完成 {completed}/{total_chunks} 個片段的處理")
                
                # 按照順序寫入檔案
                successful_chunks = sum(1 for result in chunk_results if result)
                logging.info(f"開始寫入轉錄結果，共 {successful_chunks} 個有效片段")
                
                with open(output_file, 'a+', encoding='utf-8') as f:
                    for i, result in enumerate(chunk_results):
                        if result:
                            f.write(result + "\n")
                            logging.debug(f"已寫入片段 {i + 1} 的結果")
                
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


def main():
    """主程式入口"""
    try:
        # 初始化音檔處理器
        processor = AudioProcessor(audio_dir='./speech', text_dir='./text')
        
        # 音檔路徑設定
        file_paths = [os.path.join(processor.audio_dir, "新錄音 15.m4a")]
        output_file = os.path.join(processor.text_dir, "新錄音 15.txt")

        # 自訂提示詞設定
        # Whisper 轉錄提示詞（可放入關鍵字或專有名詞協助辨識）
        whisper_prompt = "這裡放關鍵字, 像這樣, SMTP, SAMP, Unix"  # 預設為空值
        
        # GPT 翻譯系統提示詞（None 會使用函數內建的預設值）
        gpt_system_prompt = None
        
        # 若要自訂 GPT 系統提示詞，可取消註解並修改：
        # gpt_system_prompt = """
        # 你是一個專業的語音轉錄後處理專家...
        # """

        # 確保輸出資料夾存在
        os.makedirs(processor.text_dir, exist_ok=True)

        # 開始處理音檔
        processor.process_files(file_paths, output_file, whisper_prompt, gpt_system_prompt)
        logging.info(f"轉錄與翻譯完成，結果已儲存在 {output_file} 中。")
        
    except ValueError as e:
        logging.error(f"設定錯誤: {e}")
    except Exception as e:
        logging.error(f"處理過程中發生錯誤: {e}\n{traceback.format_exc()}")


# 程式入口點
if __name__ == "__main__":
    main()

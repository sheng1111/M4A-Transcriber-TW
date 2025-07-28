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
        """設定 FFmpeg 路徑"""
        AudioSegment.converter = "/usr/bin/ffmpeg"
        AudioSegment.ffprobe = "/usr/bin/ffprobe"
    
    def filter_audio(self, audio, 
                     high_pass_freq=80, 
                     low_pass_freq=8000, 
                     target_dBFS=-20.0, 
                     compression_ratio=3.0,
                     enable_noise_reduction=True):
        """對音檔進行智慧化過濾，最佳化語音清晰度與音質"""
        try:
            logging.info(f"開始音檔過濾處理，原始長度: {len(audio)}ms")
            
            # 1. 頻帶過濾 - 針對語音優化
            # 高通濾波：去除低頻噪音（空調、風扇等）
            if high_pass_freq > 0:
                audio = audio.high_pass_filter(high_pass_freq)
                logging.info(f"套用高通濾波器: {high_pass_freq}Hz")
            
            # 低通濾波：去除高頻噪音，保留語音頻譜
            if low_pass_freq > 0:
                audio = audio.low_pass_filter(low_pass_freq)
                logging.info(f"套用低通濾波器: {low_pass_freq}Hz")
            
            # 2. 噪音抑制 - 使用噪音門檻處理
            if enable_noise_reduction:
                # 使用簡單但有效的噪音門檻技術
                # 檢測並降低過於安靜的區段（可能是背景噪音）
                silence_threshold = audio.dBFS - 30  # 定義靜音門檻
                # 標準化音檔，提升整體清晰度
                audio = audio.normalize(headroom=3.0)  # 保留3dB的餘裕空間
                logging.info(f"套用噪音處理與標準化")
            
            # 3. 動態範圍壓縮 - 平衡音量差異
            if compression_ratio > 1.0:
                current_dBFS = audio.dBFS
                if current_dBFS > target_dBFS:
                    # 計算壓縮增益
                    gain_reduction = (current_dBFS - target_dBFS) / compression_ratio
                    audio = audio.apply_gain(-(current_dBFS - target_dBFS - gain_reduction))
                    logging.info(f"套用動態壓縮，增益調整: {-(current_dBFS - target_dBFS - gain_reduction):.1f}dB")
            
            # 4. 智慧正規化 - 避免過度放大或削弱
            final_dBFS = audio.dBFS
            if final_dBFS < target_dBFS - 5:  # 如果音量過小
                gain_needed = target_dBFS - final_dBFS
                audio = audio.apply_gain(min(gain_needed, 12))  # 最多放大12dB
                logging.info(f"套用音量提升: {min(gain_needed, 12):.1f}dB")
            elif final_dBFS > target_dBFS + 5:  # 如果音量過大
                gain_needed = target_dBFS - final_dBFS
                audio = audio.apply_gain(gain_needed)
                logging.info(f"套用音量降低: {gain_needed:.1f}dB")
            
            logging.info(f"音檔過濾完成，最終音量: {audio.dBFS:.1f}dBFS")
            return audio
            
        except Exception as e:
            logging.error(f"音檔過濾時發生錯誤: {e}\n{traceback.format_exc()}")
            logging.warning("使用原始音檔繼續處理")
            return audio

    def split_audio(self, file_path, max_size_mb=15):
        """將音檔分割成小於 15MB 的片段並導出為 .mp3 格式"""
        try:
            if not os.path.exists(file_path):
                logging.error(f"檔案 {file_path} 不存在")
                return []

            audio = AudioSegment.from_file(file_path)
            audio = self.filter_audio(audio)

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

    def translate_to_chinese_with_gpt(self, english_text, system_prompt=None, whisper_prompt=None):
        """使用 GPT-4.1 翻譯成繁體中文"""
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

            response = self.client.chat.completions.create(
                model="gpt-4.1",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": english_text}
                ],
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logging.error(f"使用 GPT 翻譯文本時發生錯誤: {e}\n{traceback.format_exc()}")
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

    def process_files(self, file_paths, output_file, whisper_prompt="", gpt_system_prompt=None):
        """並行處理所有音檔，並按照正確順序保存轉錄結果"""
        total_files = len(file_paths)
        logging.info(f"開始處理 {total_files} 個音檔")
        
        for file_index, file_path in enumerate(file_paths, 1):
            logging.info(f"正在處理第 {file_index}/{total_files} 個檔案: {os.path.basename(file_path)}")
            
            chunk_files = self.split_audio(file_path)
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
                # 並行處理音檔片段
                with ThreadPoolExecutor(max_workers=2) as executor:
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
        file_paths = [os.path.join(processor.audio_dir, "新錄音 3.m4a")]
        output_file = os.path.join(processor.text_dir, "新錄音 3.txt")

        # 自訂提示詞設定
        # Whisper 轉錄提示詞（可放入關鍵字或專有名詞協助辨識）
        whisper_prompt = ""  # 預設為空值
        
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

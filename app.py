import os
import traceback
import logging
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI
from pydub import AudioSegment
from tqdm import tqdm

# 設定 Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# 讀取環境變數
load_dotenv('.env')
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# 檔案目錄
AUDIO_DIR = './m4a'
TEXT_DIR = './text'

# 設定 pydub 的 FFmpeg 路徑（如果無法自動偵測）
AudioSegment.converter = "/usr/bin/ffmpeg"
AudioSegment.ffprobe = "/usr/bin/ffprobe"

def filter_audio(audio):
    """對音檔進行保守的過濾，增強語音清晰度"""
    try:
        # 高通濾波：去除低頻噪音，避免背景雜音干擾
        audio = audio.high_pass_filter(100)

        # 低通濾波：去除高頻噪音，保留語音範圍
        audio = audio.low_pass_filter(3400)

        # RMS 正規化，避免過度放大或削弱音量
        audio = audio.apply_gain(-audio.dBFS)  # 將音量歸一化

        return audio
    except Exception as e:
        logging.error(f"音檔過濾時發生錯誤: {e}\n{traceback.format_exc()}")
        return audio


def split_audio(file_path, max_size_mb=15):
    """將音檔分割成小於 15MB 的片段並導出為 .mp3 格式"""
    try:
        if not os.path.exists(file_path):
            logging.error(f"檔案 {file_path} 不存在")
            return []

        audio = AudioSegment.from_file(file_path)
        audio = filter_audio(audio)

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


def transcribe_and_translate_audio(file_path):
    """轉錄音檔"""
    try:
        with open(file_path, 'rb') as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text",
                prompt="今日關注，劉陽，杜文龍，曹衛東，福建艦，山東艦，殲-10"
            )
        return transcription.strip()
    except Exception as e:
        logging.error(f"轉錄音檔 {file_path} 時發生錯誤: {e}\n{traceback.format_exc()}")
        return ""


def translate_to_chinese_with_gpt(english_text):
    """使用 GPT-4o 翻譯成繁體中文"""
    try:
        system_prompt = (
            """
        你是一個文本校正專家，專門將文本翻譯成繁體中文（臺灣），並校正文本中的錯誤。
        翻譯時注意上下文，修正可能存在的錯誤。特別注意因語音轉文字過程而出現的小錯誤，根據語境進行合理的修正。

        # Steps

        1. **翻譯**: 將文本翻譯為繁體中文（臺灣）。
        2. **校正**: 修正潛在的文本錯誤。
        3. **過濾重複**: 刪除因即時翻譯出現的重複語句。
        4. **輸出**: 直接提供最終翻譯結果。

        # Output Format

        請直接輸出翻譯後的繁體中文文本，不提供其他說明。
            """
        )

        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": english_text}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"使用 GPT 翻譯文本時發生錯誤: {e}\n{traceback.format_exc()}")
        return ""


def filter_noise_text(text):
    """過濾轉錄結果中的常見噪聲文本"""
    noise_patterns = [
        "字幕由Amara.org社群提供",
        "字幕由Amara提供",
        "字幕由Amara",
        "Amara.org",
        "Amara",
        "字幕由",
        "社群提供"
    ]
    
    # 從最長的模式開始匹配，避免部分匹配導致的問題
    noise_patterns.sort(key=len, reverse=True)
    
    for pattern in noise_patterns:
        text = text.replace(pattern, "")
    
    return text.strip()


def process_files(file_paths, output_file):
    """並行處理所有音檔，並按照正確順序保存轉錄結果"""
    for file_path in tqdm(file_paths, desc="處理音檔"):
        chunk_files = split_audio(file_path)
        if not chunk_files:
            continue
            
        # 儲存每個分割檔案的轉錄結果
        chunk_results = [None] * len(chunk_files)
        
        def process_chunk(index, chunk_file):
            try:
                # 轉錄音檔
                raw_transcription = transcribe_and_translate_audio(chunk_file)
                if not raw_transcription:
                    return
                
                # 翻譯
                translated_text = translate_to_chinese_with_gpt(raw_transcription)
                
                # 過濾噪聲文本
                translated_text = filter_noise_text(translated_text)
                
                # 儲存結果到對應索引位置
                chunk_results[index] = translated_text
                
                # 刪除臨時檔案
                os.remove(chunk_file)
            except Exception as e:
                logging.error(f"處理分割檔案 {chunk_file} 時發生錯誤: {e}\n{traceback.format_exc()}")
        
        # 並行處理音檔片段
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(process_chunk, i, chunk_file) for i, chunk_file in enumerate(chunk_files)]
            
            # 等待所有處理完成
            for future in tqdm(futures, desc=f"處理 {os.path.basename(file_path)}", leave=False):
                future.result()
        
        # 按照順序寫入檔案
        with open(output_file, 'a+', encoding='utf-8') as f:
            for result in chunk_results:
                if result:
                    f.write(result + "\n")


# 主程式
if __name__ == "__main__":
    file_paths = [os.path.join(AUDIO_DIR, "《今日關注》 20250525 福建艦加緊海試 山東艦貼近實戰演練.mp3")]
    output_file = os.path.join(TEXT_DIR, "《今日關注》 20250525 福建艦加緊海試 山東艦貼近實戰演練.txt")

    os.makedirs(TEXT_DIR, exist_ok=True)  # 確保輸出資料夾存在

    try:
        process_files(file_paths, output_file)
        logging.info(f"轉錄與翻譯完成，結果已儲存在 {output_file} 中。")
    except Exception as e:
        logging.error(f"處理過程中發生錯誤: {e}\n{traceback.format_exc()}")

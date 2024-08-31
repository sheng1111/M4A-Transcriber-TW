from dotenv import load_dotenv
import os

from openai import OpenAI
from pydub import AudioSegment
from tqdm import tqdm

load_dotenv('.env')
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
AUDIO_DIR = './m4a'
TEXT_DIR = './text'


def filter_audio(audio):
    """對音檔進行保守的過濾"""
    try:
        # 利用高通濾波器去除低頻噪音，保留語音清晰度
        audio = audio.high_pass_filter(100)  # 削減100Hz以下的頻率，保留語音主體

        # 利應用低通濾波器去除高頻噪音
        audio = audio.low_pass_filter(3400)  # 削減3400Hz以上的頻率

        # 增益控制，增強語音部分
        audio = audio.apply_gain(5)  # 增強音量5dB，根據實際需要調整

        return audio
    except Exception as e:
        print(f"音檔過濾時發生錯誤: {e}")
        return audio  # 如果出錯，返回原始音檔


def split_audio(file_path, max_size_mb=15):
    """將音檔分割成小於 15MB 的片段並導出為 .mp3 格式"""
    try:
        audio = AudioSegment.from_file(file_path)

        # 過濾音檔
        audio = filter_audio(audio)

        file_size = os.path.getsize(file_path)
        chunk_length_ms = len(audio) * max_size_mb * 1024 * 1024 // file_size

        chunks = [audio[i:i + chunk_length_ms]
                  for i in range(0, len(audio), chunk_length_ms)]
        chunk_files = []

        for i, chunk in enumerate(chunks):
            try:
                chunk_file = f"{os.path.splitext(file_path)[0]}_chunk{i}.mp3"
                chunk.export(chunk_file, format="mp3")
                chunk_files.append(chunk_file)
            except Exception as e:
                print(f"分割音檔時發生錯誤: {e}")

        return chunk_files
    except Exception as e:
        print(f"處理音檔 {file_path} 時發生錯誤: {e}")
        return []


def transcribe_and_translate_audio(file_path):
    """轉錄並翻譯音檔函示"""
    try:
        with open(file_path, 'rb') as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="text",
                # prompt="APT, TTP, CNI, WannaCry, NCSC, GRU, MISP, RAT, Bob.com, Maltego"
            )
        return transcription
    except Exception as e:
        print(f"轉錄音檔 {file_path} 時發生錯誤: {e}")
        return ""


def translate_to_chinese_with_gpt(english_text):
    """使用 gpt-4o 進行繁體中文翻譯和後處理函示"""
    try:
        system_prompt = (
            # "你是一個專業的翻譯專家，擅長將英文本翻譯成繁體中文（臺灣）。"
            "你是一個繁體中文（臺灣）文本高手，擅長將文本錯誤地方修正。"
            "請根據上下文修正可能存在的錯誤，並使用符合臺灣習慣的詞彙和語氣來進行翻譯。"
            "請特別注意文本中可能因語音轉文字過程中的小錯誤，並根據語境進行合理的修正。"
        )

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": english_text}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"使用 GPT 翻譯文本時發生錯誤: {e}")
        return ""


def process_and_save_chunk(chunk_file, output_file):
    """處理分割檔案並即時保存轉錄和翻譯結果"""
    try:
        # 轉錄並翻譯音檔
        raw_transcription = transcribe_and_translate_audio(chunk_file)
        # 使用 GPT-4 翻譯成繁體中文
        translated_text = translate_to_chinese_with_gpt(raw_transcription)

        # 即時寫入到檔案，避免過多內容累積在記憶體中
        with open(output_file, 'a+', encoding='utf-8') as f:
            f.seek(0, os.SEEK_END)  # 確保指標在檔案末尾
            f.write(translated_text + "\n")

        # 刪除臨時的分割檔案
        try:
            os.remove(chunk_file)
        except Exception as e:
            print(f"刪除臨時檔案 {chunk_file} 時發生錯誤: {e}")
    except Exception as e:
        print(f"處理分割檔案 {chunk_file} 時發生錯誤: {e}")


def process_files(file_paths, output_file):
    """處理所有音檔並即時保存轉錄結果"""
    for file_path in tqdm(file_paths, desc="處理音檔"):
        chunk_files = split_audio(file_path)

        for chunk_file in tqdm(chunk_files, desc=f"處理 {os.path.basename(file_path)}", leave=False):
            process_and_save_chunk(chunk_file, output_file)


# 主程式
if __name__ == "__main__":
    file_paths = [
        os.path.join(AUDIO_DIR, "XXXXX.m4a"),
    ]
    output_file = os.path.join(TEXT_DIR, "XXXXX.txt")

    try:
        process_files(file_paths, output_file)
        print(f"轉錄與翻譯完成，結果已儲存在 {output_file} 中。")
    except Exception as e:
        print(f"處理過程中發生錯誤: {e}")

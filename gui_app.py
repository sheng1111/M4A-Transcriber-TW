import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from dotenv import load_dotenv
from openai import OpenAI
import threading
import logging
from app import split_audio, transcribe_and_translate_audio, translate_to_chinese_with_gpt, filter_noise_text

# 設定 Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class TranscriptionApp:
    def __init__(self, root):
        self.root = root
        self.root.title("音檔轉錄工具")
        self.root.geometry("600x400")
        
        # 載入環境變數
        load_dotenv('.env')
        self.api_key = os.getenv('OPENAI_API_KEY', '')
        
        self.setup_ui()
        
    def setup_ui(self):
        # API Key 設定
        api_frame = ttk.LabelFrame(self.root, text="API 設定", padding="10")
        api_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(api_frame, text="OpenAI API Key:").pack(side="left")
        self.api_key_entry = ttk.Entry(api_frame, width=50)
        self.api_key_entry.pack(side="left", padx=5)
        self.api_key_entry.insert(0, self.api_key)
        
        # 檔案選擇
        file_frame = ttk.LabelFrame(self.root, text="檔案設定", padding="10")
        file_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(file_frame, text="輸入音檔:").pack(side="left")
        self.input_path = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.input_path, width=40).pack(side="left", padx=5)
        ttk.Button(file_frame, text="選擇檔案", command=self.select_input_file).pack(side="left")
        
        # 輸出設定
        output_frame = ttk.LabelFrame(self.root, text="輸出設定", padding="10")
        output_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(output_frame, text="輸出檔名:").pack(side="left")
        self.output_name = tk.StringVar()
        ttk.Entry(output_frame, textvariable=self.output_name, width=40).pack(side="left", padx=5)
        
        # 進度條
        self.progress = ttk.Progressbar(self.root, mode='indeterminate')
        self.progress.pack(fill="x", padx=10, pady=5)
        
        # 狀態標籤
        self.status_label = ttk.Label(self.root, text="就緒")
        self.status_label.pack(pady=5)
        
        # 開始按鈕
        self.start_button = ttk.Button(self.root, text="開始轉錄", command=self.start_transcription)
        self.start_button.pack(pady=10)
        
    def select_input_file(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("音訊檔案", "*.mp3 *.m4a *.wav")]
        )
        if file_path:
            self.input_path.set(file_path)
            # 自動設定輸出檔名
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            self.output_name.set(f"{base_name}.txt")
    
    def start_transcription(self):
        if not self.api_key_entry.get():
            messagebox.showerror("錯誤", "請輸入 OpenAI API Key")
            return
            
        if not self.input_path.get():
            messagebox.showerror("錯誤", "請選擇輸入音檔")
            return
            
        if not self.output_name.get():
            messagebox.showerror("錯誤", "請設定輸出檔名")
            return
        
        # 禁用開始按鈕
        self.start_button.config(state="disabled")
        self.progress.start()
        self.status_label.config(text="處理中...")
        
        # 在新執行緒中執行轉錄
        thread = threading.Thread(target=self.process_transcription)
        thread.start()
    
    def process_transcription(self):
        try:
            # 設定 API key
            client = OpenAI(api_key=self.api_key_entry.get())
            
            # 處理音檔
            chunk_files = split_audio(self.input_path.get())
            if not chunk_files:
                raise Exception("音檔分割失敗")
            
            # 建立輸出目錄
            output_dir = os.path.dirname(self.output_name.get())
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            # 處理每個分割檔案
            with open(self.output_name.get(), 'w', encoding='utf-8') as f:
                for chunk_file in chunk_files:
                    # 轉錄
                    raw_transcription = transcribe_and_translate_audio(chunk_file)
                    if raw_transcription:
                        # 翻譯
                        translated_text = translate_to_chinese_with_gpt(raw_transcription)
                        # 過濾噪聲
                        translated_text = filter_noise_text(translated_text)
                        # 寫入檔案
                        f.write(translated_text + "\n")
                    
                    # 刪除臨時檔案
                    os.remove(chunk_file)
            
            self.root.after(0, self.show_success)
            
        except Exception as e:
            logging.error(f"處理過程中發生錯誤: {str(e)}")
            self.root.after(0, lambda: self.show_error(str(e)))
    
    def show_success(self):
        self.progress.stop()
        self.status_label.config(text="轉錄完成！")
        self.start_button.config(state="normal")
        messagebox.showinfo("完成", "轉錄已完成！")
    
    def show_error(self, error_msg):
        self.progress.stop()
        self.status_label.config(text="處理失敗")
        self.start_button.config(state="normal")
        messagebox.showerror("錯誤", f"處理過程中發生錯誤：\n{error_msg}")

if __name__ == "__main__":
    root = tk.Tk()
    app = TranscriptionApp(root)
    root.mainloop() 
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import logging
import inspect
from pathlib import Path
from dotenv import load_dotenv, set_key
from app import AudioProcessor

# 設定 Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class TranscriptionApp:
    """音檔轉錄GUI應用程式"""

    def __init__(self, root):
        """初始化應用程式"""
        self.root = root
        self.audio_processor = None
        self.is_processing = False
        self.should_stop = False  # 新增：停止處理標誌
        self.processing_thread = None
        self.defaults = self._load_defaults()
        self.api_key_visible = False
        self.current_file_index = 0  # 新增：當前處理檔案索引
        self.total_files = 0  # 新增：總檔案數
        self.current_chunk = 0  # 新增：當前處理片段
        self.total_chunks = 0  # 新增：總片段數
        self.setup_window()
        self.setup_ui()
        self.setup_logging_handler()
        self._load_api_key()
        
    def _load_defaults(self):
        """從 AudioProcessor 載入預設值"""
        defaults = {}
        
        # 從 AudioProcessor.__init__ 取得預設路徑
        init_signature = inspect.signature(AudioProcessor.__init__)
        defaults['audio_dir'] = init_signature.parameters['audio_dir'].default
        defaults['text_dir'] = init_signature.parameters['text_dir'].default
        
        # 從 split_audio 方法取得預設分割大小
        split_signature = inspect.signature(AudioProcessor.split_audio)
        defaults['max_size_mb'] = split_signature.parameters['max_size_mb'].default
        
        # 從 filter_audio 方法取得預設音檔過濾參數
        filter_signature = inspect.signature(AudioProcessor.filter_audio)
        defaults['high_pass_freq'] = filter_signature.parameters['high_pass_freq'].default
        defaults['low_pass_freq'] = filter_signature.parameters['low_pass_freq'].default
        defaults['target_dBFS'] = filter_signature.parameters['target_dBFS'].default
        defaults['compression_ratio'] = filter_signature.parameters['compression_ratio'].default
        defaults['enable_noise_reduction'] = filter_signature.parameters['enable_noise_reduction'].default
        
        # 從 AudioProcessor 源碼中提取預設 GPT 系統提示詞
        defaults['gpt_system_prompt'] = """你是一個專業的文本校正和翻譯專家，專門處理whisper語音轉文字後的內容，將文本翻譯成繁體中文（臺灣），並進行校正和分段。
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

直接輸出分段後的繁體中文文本，段落間用空行分隔。不需要其他說明。"""
        
        return defaults
    
    def _load_api_key(self):
        """從.env檔案載入API Key"""
        try:
            load_dotenv('.env')
            api_key = os.getenv('OPENAI_API_KEY', '')
            if api_key:
                self.api_key_entry.delete(0, tk.END)
                self.api_key_entry.insert(0, api_key)
                self._toggle_api_key_visibility(show=False)  # 預設隱藏
                logging.info("已從 .env 檔案載入 API Key")
            else:
                logging.info("未在 .env 檔案中找到 API Key")
        except Exception as e:
            logging.warning(f"載入 .env 檔案時發生錯誤: {e}")
    
    def _save_api_key(self):
        """儲存API Key到.env檔案"""
        try:
            api_key = self.api_key_entry.get().strip()
            if api_key:
                # 確保.env檔案存在
                env_file = '.env'
                if not os.path.exists(env_file):
                    with open(env_file, 'w') as f:
                        f.write('')
                
                # 設定API Key
                set_key(env_file, 'OPENAI_API_KEY', api_key)
                self.update_status("API Key 已儲存")
                messagebox.showinfo("儲存成功", "API Key 已儲存至 .env 檔案")
                logging.info("API Key 已儲存至 .env 檔案")
            else:
                messagebox.showerror("錯誤", "請輸入有效的 API Key")
        except Exception as e:
            messagebox.showerror("錯誤", f"儲存 API Key 時發生錯誤：{str(e)}")
            logging.error(f"儲存 API Key 時發生錯誤: {e}")
    
    def _toggle_api_key_visibility(self, show=None):
        """切換API Key顯示/隱藏"""
        if show is None:
            self.api_key_visible = not self.api_key_visible
        else:
            self.api_key_visible = show
            
        if self.api_key_visible:
            self.api_key_entry.config(show="")
            self.toggle_key_btn.config(text="隱藏")
        else:
            self.api_key_entry.config(show="*")
            self.toggle_key_btn.config(text="顯示")
        
    def setup_window(self):
        """設定主視窗"""
        self.root.title("M4A 音檔轉文字工具")
        self.root.geometry("800x900")
        self.root.minsize(600, 500)
        
        # 設定視窗主題
        style = ttk.Style()
        style.theme_use('clam')
        
    def setup_ui(self):
        """設定使用者介面"""
        # 主容器
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill="both", expand=True)
        
        # 建立標籤頁
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill="both", expand=True)
        
        # 基本設定頁面（包含API設定）
        self.setup_basic_tab()
        
        # 進階設定頁面
        self.setup_advanced_tab()
        
        # 結果檢視頁面
        self.setup_result_tab()
        
        # 日誌頁面
        self.setup_log_tab()
        
        # 底部控制區
        self.setup_control_area(main_frame)
    

        
    def setup_basic_tab(self):
        """設定基本設定頁面（包含API設定）"""
        basic_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(basic_frame, text="基本設定")
        
        # OpenAI API 設定
        openai_section = ttk.LabelFrame(basic_frame, text="OpenAI API 設定", padding="10")
        openai_section.pack(fill="x", pady=(0, 10))
        
        # API Key 輸入
        key_frame = ttk.Frame(openai_section)
        key_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(key_frame, text="API Key:").pack(side="left")
        self.api_key_entry = ttk.Entry(key_frame, width=50, show="*")
        self.api_key_entry.pack(side="left", padx=(5, 5), fill="x", expand=True)
        
        self.toggle_key_btn = ttk.Button(key_frame, text="顯示", width=8, command=self._toggle_api_key_visibility)
        self.toggle_key_btn.pack(side="left", padx=(0, 5))
        
        ttk.Button(key_frame, text="儲存", command=self._save_api_key).pack(side="left")
        
        # API 說明
        info_frame = ttk.Frame(openai_section)
        info_frame.pack(fill="x")
        
        info_text = """使用說明：
• 請在上方輸入您的 OpenAI API Key
• API Key 會自動儲存至 .env 檔案中
• 請確保您的 API Key 有足夠的額度使用 Whisper 和 GPT 服務
• 如需申請 API Key，請至 https://platform.openai.com/api-keys"""
        
        info_label = tk.Label(info_frame, text=info_text, 
                             justify="left", font=("Arial", 9), 
                             bg="#e8f4fd", relief="solid", borderwidth=1, padx=10, pady=8)
        info_label.pack(fill="x")
        
        # 檔案選擇區
        file_section = ttk.LabelFrame(basic_frame, text="檔案設定", padding="10")
        file_section.pack(fill="x", pady=(0, 10))
        
        # 輸入檔案
        input_frame = ttk.Frame(file_section)
        input_frame.pack(fill="x", pady=(0, 5))
        ttk.Label(input_frame, text="輸入音檔:").pack(side="left")
        self.input_files = []
        self.input_listbox = tk.Listbox(file_section, height=4)
        self.input_listbox.pack(fill="x", pady=(5, 0))
        
        input_btn_frame = ttk.Frame(file_section)
        input_btn_frame.pack(fill="x", pady=(5, 0))
        ttk.Button(input_btn_frame, text="新增檔案", command=self.add_input_files).pack(side="left", padx=(0, 5))
        ttk.Button(input_btn_frame, text="新增資料夾", command=self.add_input_folder).pack(side="left", padx=(0, 5))
        ttk.Button(input_btn_frame, text="清除列表", command=self.clear_input_files).pack(side="left")
        
        # 輸出設定
        output_frame = ttk.Frame(file_section)
        output_frame.pack(fill="x", pady=(10, 0))
        ttk.Label(output_frame, text="輸出資料夾:").pack(side="left")
        self.output_dir = tk.StringVar(value=self.defaults['text_dir'])
        ttk.Entry(output_frame, textvariable=self.output_dir, width=50).pack(side="left", padx=(5, 5))
        ttk.Button(output_frame, text="選擇", command=self.select_output_dir).pack(side="left")
        
        # 音檔處理設定
        audio_section = ttk.LabelFrame(basic_frame, text="音檔處理設定", padding="10")
        audio_section.pack(fill="x", pady=(0, 10))

        # 分割大小設定
        split_frame = ttk.Frame(audio_section)
        split_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(split_frame, text=f"分割大小 (MB):").pack(side="left")
        self.max_size_mb = tk.IntVar(value=self.defaults['max_size_mb'])
        size_spinbox = ttk.Spinbox(split_frame, from_=5, to=25, width=10, textvariable=self.max_size_mb)
        size_spinbox.pack(side="left", padx=(5, 0))
        ttk.Label(split_frame, text=f" [預設: {self.defaults['max_size_mb']} MB]", font=("Arial", 9)).pack(side="left", padx=(5, 0))

        # 音檔過濾參數 - 可編輯
        ttk.Label(audio_section, text="音檔過濾參數（進階）：", font=("Arial", 10, "bold")).pack(anchor="w", pady=(5, 5))

        # 建立兩欄佈局
        params_container = ttk.Frame(audio_section)
        params_container.pack(fill="x")

        left_col = ttk.Frame(params_container)
        left_col.pack(side="left", fill="x", expand=True, padx=(0, 10))

        right_col = ttk.Frame(params_container)
        right_col.pack(side="left", fill="x", expand=True)

        # 左欄 - 頻率設定
        # 高通濾波
        hp_frame = ttk.Frame(left_col)
        hp_frame.pack(fill="x", pady=2)
        ttk.Label(hp_frame, text="高通濾波 (Hz):").pack(side="left")
        self.high_pass_freq = tk.IntVar(value=self.defaults['high_pass_freq'])
        hp_spinbox = ttk.Spinbox(hp_frame, from_=0, to=500, width=10, textvariable=self.high_pass_freq)
        hp_spinbox.pack(side="left", padx=(5, 5))
        ttk.Label(hp_frame, text="去除低頻噪音", font=("Arial", 8), foreground="gray").pack(side="left")

        # 低通濾波
        lp_frame = ttk.Frame(left_col)
        lp_frame.pack(fill="x", pady=2)
        ttk.Label(lp_frame, text="低通濾波 (Hz):").pack(side="left")
        self.low_pass_freq = tk.IntVar(value=self.defaults['low_pass_freq'])
        lp_spinbox = ttk.Spinbox(lp_frame, from_=3000, to=20000, width=10, increment=1000, textvariable=self.low_pass_freq)
        lp_spinbox.pack(side="left", padx=(5, 5))
        ttk.Label(lp_frame, text="保留語音頻譜", font=("Arial", 8), foreground="gray").pack(side="left")

        # 右欄 - 音量設定
        # 目標音量
        dbfs_frame = ttk.Frame(right_col)
        dbfs_frame.pack(fill="x", pady=2)
        ttk.Label(dbfs_frame, text="目標音量 (dBFS):").pack(side="left")
        self.target_dBFS = tk.DoubleVar(value=self.defaults['target_dBFS'])
        dbfs_spinbox = ttk.Spinbox(dbfs_frame, from_=-30.0, to=-10.0, width=10, increment=1.0, textvariable=self.target_dBFS)
        dbfs_spinbox.pack(side="left", padx=(5, 5))
        ttk.Label(dbfs_frame, text="標準化音量", font=("Arial", 8), foreground="gray").pack(side="left")

        # 壓縮比例
        comp_frame = ttk.Frame(right_col)
        comp_frame.pack(fill="x", pady=2)
        ttk.Label(comp_frame, text="壓縮比例:").pack(side="left")
        self.compression_ratio = tk.DoubleVar(value=self.defaults['compression_ratio'])
        comp_spinbox = ttk.Spinbox(comp_frame, from_=1.0, to=10.0, width=10, increment=0.5, textvariable=self.compression_ratio)
        comp_spinbox.pack(side="left", padx=(5, 5))
        ttk.Label(comp_frame, text="平衡音量差異", font=("Arial", 8), foreground="gray").pack(side="left")

        # 選項區
        options_frame = ttk.Frame(audio_section)
        options_frame.pack(fill="x", pady=(10, 0))

        self.enable_noise_reduction = tk.BooleanVar(value=self.defaults['enable_noise_reduction'])
        ttk.Checkbutton(options_frame, text="啟用降噪處理", variable=self.enable_noise_reduction).pack(side="left", padx=(0, 15))

        self.voice_boost = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="增強語音頻段 (300-3400Hz)", variable=self.voice_boost).pack(side="left")

        # 重設按鈕
        reset_btn_frame = ttk.Frame(audio_section)
        reset_btn_frame.pack(fill="x", pady=(5, 0))
        ttk.Button(reset_btn_frame, text="重設為預設值", command=self.reset_audio_params).pack(side="left")
        
    def setup_advanced_tab(self):
        """設定進階設定頁面"""
        advanced_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(advanced_frame, text="進階設定")
        
        # Whisper 設定
        whisper_section = ttk.LabelFrame(advanced_frame, text="Whisper 轉錄設定", padding="10")
        whisper_section.pack(fill="x", pady=(0, 10))
        
        ttk.Label(whisper_section, text="轉錄提示詞 (可輸入專有名詞協助辨識):").pack(anchor="w")
        self.whisper_prompt = tk.Text(whisper_section, height=3, wrap="word")
        self.whisper_prompt.pack(fill="x", pady=(5, 0))
        
        # GPT 設定
        gpt_section = ttk.LabelFrame(advanced_frame, text="GPT 翻譯潤飾設定", padding="10")
        gpt_section.pack(fill="both", expand=True)
        
        ttk.Label(gpt_section, text="GPT 系統提示詞 (可直接編輯修改):").pack(anchor="w")
        self.gpt_system_prompt = scrolledtext.ScrolledText(gpt_section, height=12, wrap="word")
        self.gpt_system_prompt.pack(fill="both", expand=True, pady=(5, 0))
        
        # 使用從 AudioProcessor 載入的預設提示詞
        self.gpt_system_prompt.delete("1.0", tk.END)
        self.gpt_system_prompt.insert("1.0", self.defaults['gpt_system_prompt'])
        
        # 重設按鈕
        reset_frame = ttk.Frame(gpt_section)
        reset_frame.pack(fill="x", pady=(5, 0))
        ttk.Button(reset_frame, text="重設為預設值", command=self.reset_gpt_prompt).pack(side="left")
        
    def reset_gpt_prompt(self):
        """重設GPT提示詞為預設值"""
        self.gpt_system_prompt.delete("1.0", tk.END)
        self.gpt_system_prompt.insert("1.0", self.defaults['gpt_system_prompt'])
        self.update_status("GPT 系統提示詞已重設為預設值")

    def reset_audio_params(self):
        """重設音檔過濾參數為預設值"""
        self.high_pass_freq.set(self.defaults['high_pass_freq'])
        self.low_pass_freq.set(self.defaults['low_pass_freq'])
        self.target_dBFS.set(self.defaults['target_dBFS'])
        self.compression_ratio.set(self.defaults['compression_ratio'])
        self.enable_noise_reduction.set(self.defaults['enable_noise_reduction'])
        self.voice_boost.set(True)
        self.update_status("音檔過濾參數已重設為預設值")
        messagebox.showinfo("重設成功", "音檔過濾參數已重設為預設值")
        
    def setup_result_tab(self):
        """設定結果檢視頁面"""
        result_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(result_frame, text="結果檢視")
        
        # 結果列表
        result_list_frame = ttk.LabelFrame(result_frame, text="轉錄結果", padding="10")
        result_list_frame.pack(fill="x", pady=(0, 10))
        
        self.result_listbox = tk.Listbox(result_list_frame, height=6)
        self.result_listbox.pack(fill="x", pady=(5, 0))
        self.result_listbox.bind('<Double-Button-1>', self.on_result_select)
        self.result_listbox.bind('<<ListboxSelect>>', self.on_result_select)
        
        result_btn_frame = ttk.Frame(result_list_frame)
        result_btn_frame.pack(fill="x", pady=(5, 0))
        
        ttk.Button(result_btn_frame, text="重新整理", command=self.load_results).pack(side="left", padx=(0, 5))
        ttk.Button(result_btn_frame, text="清除列表", command=self.clear_results).pack(side="left")
        
        # 結果內容顯示區
        result_content_frame = ttk.LabelFrame(result_frame, text="結果內容", padding="10")
        result_content_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        self.result_text = scrolledtext.ScrolledText(result_content_frame, height=15, wrap="word")
        self.result_text.pack(fill="both", expand=True, pady=(0, 5))
        
        # 結果操作按鈕
        result_control_frame = ttk.Frame(result_content_frame)
        result_control_frame.pack(fill="x")
        
        ttk.Button(result_control_frame, text="儲存修改", command=self.save_current_result).pack(side="left", padx=(0, 5))
        ttk.Button(result_control_frame, text="複製內容", command=self.copy_result_to_clipboard).pack(side="left", padx=(0, 5))
        ttk.Button(result_control_frame, text="匯出檔案", command=self.export_result).pack(side="left", padx=(0, 5))
        
        # 顯示當前檔案名稱
        self.current_result_file = tk.StringVar(value="未選擇檔案")
        current_file_label = ttk.Label(result_control_frame, textvariable=self.current_result_file, font=("Arial", 9))
        current_file_label.pack(side="right")
        
    def load_results(self):
        """載入轉錄結果"""
        if not self.output_dir.get():
            messagebox.showerror("錯誤", "請先設定輸出資料夾")
            return

        # 只載入根目錄的 .txt 檔案，排除子目錄（如 OLD 資料夾）
        text_files = [f for f in Path(self.output_dir.get()).glob("*.txt") if f.is_file()]
        if not text_files:
            messagebox.showinfo("資訊", "輸出資料夾中沒有找到轉錄結果檔案。")
            return

        self.result_listbox.delete(0, tk.END)
        for file_path in text_files:
            self.result_listbox.insert(tk.END, file_path.name)

        self.update_status(f"已載入 {len(text_files)} 個轉錄結果檔案")
            
    def clear_results(self):
        """清除轉錄結果"""
        self.result_listbox.delete(0, tk.END)
        self.result_text.delete("1.0", tk.END)
        self.current_result_file.set("未選擇檔案")
        self.update_status("已清除所有轉錄結果")
        
    def on_result_select(self, event=None):
        """當選擇結果列表項目時載入文件內容"""
        selection = self.result_listbox.curselection()
        if not selection:
            return
            
        selected_file = self.result_listbox.get(selection[0])
        file_path = Path(self.output_dir.get()) / selected_file
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            self.result_text.delete("1.0", tk.END)
            self.result_text.insert("1.0", content)
            self.current_result_file.set(f"檔案: {selected_file}")
            self.update_status(f"已載入: {selected_file}")
            
        except Exception as e:
            messagebox.showerror("錯誤", f"載入檔案時發生錯誤：{str(e)}")
            logging.error(f"載入結果檔案 {file_path} 時發生錯誤: {e}")
    
    def save_current_result(self):
        """儲存當前編輯的結果"""
        current_file = self.current_result_file.get()
        if current_file == "未選擇檔案":
            messagebox.showerror("錯誤", "請先選擇一個結果檔案")
            return
        
        file_name = current_file.replace("檔案: ", "")
        file_path = Path(self.output_dir.get()) / file_name
        
        try:
            content = self.result_text.get("1.0", tk.END).strip()
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            messagebox.showinfo("儲存成功", f"已儲存修改至: {file_name}")
            self.update_status(f"已儲存修改: {file_name}")
            
        except Exception as e:
            messagebox.showerror("錯誤", f"儲存檔案時發生錯誤：{str(e)}")
            logging.error(f"儲存結果檔案 {file_path} 時發生錯誤: {e}")
    
    def copy_result_to_clipboard(self):
        """複製結果內容到剪貼簿"""
        content = self.result_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("警告", "沒有內容可複製")
            return
        
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self.root.update()  # 更新剪貼簿
            messagebox.showinfo("複製成功", "內容已複製到剪貼簿")
            self.update_status("內容已複製到剪貼簿")
            
        except Exception as e:
            messagebox.showerror("錯誤", f"複製到剪貼簿時發生錯誤：{str(e)}")
    
    def export_result(self):
        """匯出結果到新檔案"""
        content = self.result_text.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("警告", "沒有內容可匯出")
            return
        
        file_path = filedialog.asksaveasfilename(
            title="匯出轉錄結果",
            defaultextension=".txt",
            filetypes=[
                ("文字檔案", "*.txt"),
                ("Markdown檔案", "*.md"),
                ("所有檔案", "*.*")
            ]
        )
        
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                messagebox.showinfo("匯出成功", f"結果已匯出至：{file_path}")
                self.update_status(f"已匯出至: {os.path.basename(file_path)}")
                
            except Exception as e:
                messagebox.showerror("錯誤", f"匯出檔案時發生錯誤：{str(e)}")
                logging.error(f"匯出結果檔案 {file_path} 時發生錯誤: {e}")
        
    def setup_log_tab(self):
        """設定日誌頁面"""
        log_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(log_frame, text="處理日誌")
        
        # 日誌顯示區
        log_label_frame = ttk.LabelFrame(log_frame, text="處理進度與日誌", padding="5")
        log_label_frame.pack(fill="both", expand=True)
        
        self.log_text = scrolledtext.ScrolledText(log_label_frame, height=20, state="disabled")
        self.log_text.pack(fill="both", expand=True)
        
        # 日誌控制按鈕
        log_btn_frame = ttk.Frame(log_frame)
        log_btn_frame.pack(fill="x", pady=(10, 0))
        ttk.Button(log_btn_frame, text="清除日誌", command=self.clear_log).pack(side="left")
        ttk.Button(log_btn_frame, text="儲存日誌", command=self.save_log).pack(side="left", padx=(5, 0))
        
    def setup_control_area(self, parent):
        """設定控制區域"""
        control_frame = ttk.Frame(parent, padding="10")
        control_frame.pack(fill="x", side="bottom")
        
        # 進度條
        progress_frame = ttk.LabelFrame(control_frame, text="處理進度", padding="5")
        progress_frame.pack(fill="x", pady=(0, 10))
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill="x", pady=(0, 5))
        
        self.status_label = ttk.Label(progress_frame, text="就緒")
        self.status_label.pack()
        
        # 控制按鈕
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(fill="x")
        
        self.start_button = ttk.Button(button_frame, text="開始轉錄", command=self.start_transcription)
        self.start_button.pack(side="left", padx=(0, 10))
        
        self.stop_button = ttk.Button(button_frame, text="停止處理", command=self.stop_transcription, state="disabled")
        self.stop_button.pack(side="left", padx=(0, 10))
        
        ttk.Button(button_frame, text="測試連線", command=self.test_connection).pack(side="left", padx=(0, 10))
        ttk.Button(button_frame, text="重載預設值", command=self.reload_defaults).pack(side="left", padx=(0, 10))
        ttk.Button(button_frame, text="關於", command=self.show_about).pack(side="right")
        
    def setup_logging_handler(self):
        """設定日誌處理器"""
        self.log_handler = GuiLogHandler(self.log_text)
        self.log_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        self.log_handler.setFormatter(formatter)
        logging.getLogger().addHandler(self.log_handler)
        
    def reload_defaults(self):
        """重新載入 AudioProcessor 預設值"""
        try:
            self.defaults = self._load_defaults()
            # 更新UI顯示
            self.output_dir.set(self.defaults['text_dir'])
            self.max_size_mb.set(self.defaults['max_size_mb'])
            
            # 更新GPT系統提示詞
            self.gpt_system_prompt.delete("1.0", tk.END)
            self.gpt_system_prompt.insert("1.0", self.defaults['gpt_system_prompt'])
            
            self.update_status("已重載 AudioProcessor 預設值")
            messagebox.showinfo("預設值", "已成功重載 AudioProcessor 的最新預設值")
        except Exception as e:
            messagebox.showerror("錯誤", f"重載預設值時發生錯誤：{str(e)}")
        
    def add_input_files(self):
        """新增輸入檔案"""
        files = filedialog.askopenfilenames(
            title="選擇音檔",
            filetypes=[
                ("音檔", "*.mp3 *.m4a *.wav *.flac *.aac"),
                ("所有檔案", "*.*")
            ]
        )
        for file in files:
            if file not in self.input_files:
                self.input_files.append(file)
                self.input_listbox.insert(tk.END, os.path.basename(file))
        
    def add_input_folder(self):
        """新增資料夾中的音檔"""
        folder = filedialog.askdirectory(title="選擇包含音檔的資料夾")
        if folder:
            audio_extensions = {'.mp3', '.m4a', '.wav', '.flac', '.aac'}
            for file_path in Path(folder).rglob('*'):
                if file_path.suffix.lower() in audio_extensions:
                    file_str = str(file_path)
                    if file_str not in self.input_files:
                        self.input_files.append(file_str)
                        self.input_listbox.insert(tk.END, file_path.name)
        
    def clear_input_files(self):
        """清除輸入檔案列表"""
        self.input_files.clear()
        self.input_listbox.delete(0, tk.END)
        
    def select_output_dir(self):
        """選擇輸出資料夾"""
        directory = filedialog.askdirectory(title="選擇輸出資料夾")
        if directory:
            self.output_dir.set(directory)
            
    def test_connection(self):
        """測試 OpenAI API 連線"""
        try:
            # 檢查API Key
            api_key = self.api_key_entry.get().strip()
            if not api_key:
                messagebox.showerror("錯誤", "請先設定 OpenAI API Key")
                return
                
            self.update_status("測試連線中...")
            
            # 暫時設定環境變數進行測試
            os.environ['OPENAI_API_KEY'] = api_key
            test_processor = AudioProcessor()
            
            self.update_status("連線測試成功")
            messagebox.showinfo("連線測試", "OpenAI API 連線正常")
        except Exception as e:
            self.update_status("連線測試失敗")
            messagebox.showerror("連線測試", f"連線失敗：{str(e)}")
            
    def start_transcription(self):
        """開始轉錄處理"""
        # 1. 驗證 API Key
        api_key = self.api_key_entry.get().strip()
        if not api_key:
            messagebox.showerror("錯誤", "請先設定 OpenAI API Key")
            self.notebook.select(0)  # 切換到基本設定頁面
            return

        # 2. 驗證輸入檔案
        if not self.input_files:
            messagebox.showerror("錯誤", "請選擇至少一個音檔")
            self.notebook.select(0)  # 切換到基本設定頁面
            return

        # 3. 驗證檔案是否存在
        missing_files = [f for f in self.input_files if not os.path.exists(f)]
        if missing_files:
            messagebox.showerror("錯誤",
                               f"以下檔案不存在：\n{chr(10).join(os.path.basename(f) for f in missing_files[:5])}"
                               + (f"\n... 還有 {len(missing_files)-5} 個檔案" if len(missing_files) > 5 else ""))
            return

        # 4. 驗證輸出資料夾
        if not self.output_dir.get():
            messagebox.showerror("錯誤", "請設定輸出資料夾")
            self.notebook.select(0)  # 切換到基本設定頁面
            return

        # 5. 確保輸出資料夾存在且可寫入
        try:
            os.makedirs(self.output_dir.get(), exist_ok=True)
            # 測試寫入權限
            test_file = os.path.join(self.output_dir.get(), '.write_test')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
        except Exception as e:
            messagebox.showerror("錯誤", f"無法寫入輸出資料夾：{self.output_dir.get()}\n錯誤：{str(e)}")
            return

        # 6. 確認開始處理
        file_count = len(self.input_files)
        total_size = sum(os.path.getsize(f) for f in self.input_files) / (1024*1024)  # MB
        confirm_msg = f"準備處理 {file_count} 個音檔（總大小 {total_size:.1f} MB）\n\n是否開始轉錄？"

        if not messagebox.askyesno("確認開始", confirm_msg):
            return

        # 7. 設定UI狀態
        self.is_processing = True
        self.should_stop = False
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.progress_var.set(0)
        self.total_files = file_count
        self.current_file_index = 0
        self.update_status("初始化處理...")

        # 8. 切換到日誌頁面
        self.notebook.select(3)  # 日誌頁面現在是第4個

        # 9. 在新執行緒中執行轉錄
        self.processing_thread = threading.Thread(target=self.process_transcription)
        self.processing_thread.daemon = True
        self.processing_thread.start()

    def stop_transcription(self):
        """停止轉錄處理"""
        if not self.is_processing:
            return

        if messagebox.askyesno("確認停止", "確定要停止處理嗎？\n已完成的檔案會被保留。"):
            self.should_stop = True
            self.is_processing = False
            self.stop_button.config(state="disabled")
            self.update_status("正在停止處理，請稍候...")
            logging.warning("使用者要求停止處理")
        
    def process_transcription(self):
        """執行轉錄處理 - 全部委託給 AudioProcessor"""
        completed_files = []
        failed_files = []

        try:
            # 設定API Key到環境變數
            api_key = self.api_key_entry.get().strip()
            os.environ['OPENAI_API_KEY'] = api_key

            # 收集用戶設定
            whisper_prompt = self.whisper_prompt.get("1.0", tk.END).strip()
            gpt_system_prompt = self.gpt_system_prompt.get("1.0", tk.END).strip()

            # 收集音檔過濾參數
            audio_filter_params = {
                'high_pass_freq': self.high_pass_freq.get(),
                'low_pass_freq': self.low_pass_freq.get(),
                'target_dBFS': self.target_dBFS.get(),
                'compression_ratio': self.compression_ratio.get(),
                'enable_noise_reduction': self.enable_noise_reduction.get(),
                'voice_boost': self.voice_boost.get()
            }

            logging.info(f"音檔過濾參數: {audio_filter_params}")

            # 初始化 AudioProcessor
            self.audio_processor = AudioProcessor(text_dir=self.output_dir.get())

            self.total_files = len(self.input_files)

            # 逐一處理每個檔案
            for file_index, file_path in enumerate(self.input_files):
                # 檢查是否應該停止
                if self.should_stop or not self.is_processing:
                    self.root.after(0, lambda: self.update_status(f"處理已停止 - 已完成 {len(completed_files)}/{self.total_files} 個檔案"))
                    break

                self.current_file_index = file_index + 1
                base_name = os.path.basename(file_path)

                # 更新狀態
                status_msg = f"處理檔案 {self.current_file_index}/{self.total_files}: {base_name}"
                self.root.after(0, lambda msg=status_msg: self.update_status(msg))
                logging.info(f"{'='*60}")
                logging.info(status_msg)
                logging.info(f"{'='*60}")

                # 更新整體進度
                progress = (file_index / self.total_files) * 100
                self.root.after(0, lambda p=progress: self.progress_var.set(p))

                try:
                    # 產生輸出檔名
                    output_base_name = os.path.splitext(base_name)[0]
                    output_file = os.path.join(self.output_dir.get(), f"{output_base_name}.txt")

                    # 完全委託給 AudioProcessor 處理，包含音檔過濾參數
                    self.audio_processor.process_files(
                        file_paths=[file_path],
                        output_file=output_file,
                        whisper_prompt=whisper_prompt,
                        gpt_system_prompt=gpt_system_prompt if gpt_system_prompt.strip() else None,
                        **audio_filter_params  # 傳遞音檔過濾參數
                    )

                    completed_files.append(base_name)
                    logging.info(f"✓ 檔案處理完成: {base_name}")

                except Exception as file_error:
                    failed_files.append((base_name, str(file_error)))
                    logging.error(f"✗ 檔案處理失敗: {base_name}")
                    logging.error(f"錯誤詳情: {file_error}")

                    # 詢問是否繼續處理下一個檔案
                    if file_index < self.total_files - 1:  # 如果還有下一個檔案
                        should_continue = messagebox.askyesno(
                            "處理錯誤",
                            f"處理 {base_name} 時發生錯誤：\n{str(file_error)}\n\n是否繼續處理剩餘檔案？"
                        )
                        if not should_continue:
                            self.should_stop = True
                            break

            # 處理完成
            if not self.should_stop:
                self.root.after(0, lambda: self.progress_var.set(100))
                self.root.after(0, lambda: self.show_completion(completed_files, failed_files))
            else:
                self.root.after(0, lambda: self.show_partial_completion(completed_files, failed_files))

        except Exception as e:
            # 錯誤處理
            logging.error(f"GUI處理過程發生嚴重錯誤: {e}")
            import traceback
            logging.error(traceback.format_exc())
            self.root.after(0, lambda err=str(e): self.show_error(err))
        finally:
            self.root.after(0, self.reset_ui_state)
            
    def update_status(self, message):
        """更新狀態顯示"""
        self.status_label.config(text=message)
        
    def show_completion(self, completed_files, failed_files):
        """顯示完成訊息"""
        self.update_status("轉錄完成")

        # 切換到結果檢視頁面並載入結果
        self.notebook.select(2)  # 結果檢視頁面是第3個標籤頁
        self.load_results()

        # 建立詳細的完成訊息
        msg = f"轉錄完成！\n\n"
        msg += f"成功: {len(completed_files)} 個檔案\n"
        if failed_files:
            msg += f"失敗: {len(failed_files)} 個檔案\n"
        msg += f"\n結果儲存在：{self.output_dir.get()}"

        if failed_files:
            msg += f"\n\n失敗檔案："
            for fname, _ in failed_files[:3]:  # 只顯示前3個
                msg += f"\n• {fname}"
            if len(failed_files) > 3:
                msg += f"\n... 還有 {len(failed_files)-3} 個"

        messagebox.showinfo("完成", msg)

    def show_partial_completion(self, completed_files, failed_files):
        """顯示部分完成訊息"""
        self.update_status("處理已停止")

        # 切換到結果檢視頁面並載入結果
        if completed_files:
            self.notebook.select(2)  # 結果檢視頁面是第3個標籤頁
            self.load_results()

        msg = f"處理已停止\n\n"
        msg += f"已完成: {len(completed_files)}/{self.total_files} 個檔案\n"
        if failed_files:
            msg += f"失敗: {len(failed_files)} 個檔案\n"
        msg += f"\n已完成的結果已儲存在：{self.output_dir.get()}"

        messagebox.showwarning("部分完成", msg)

    def show_error(self, error_msg):
        """顯示錯誤訊息"""
        self.update_status("處理失敗")
        messagebox.showerror("錯誤", f"處理過程發生錯誤：\n{error_msg}")
        
    def reset_ui_state(self):
        """重設UI狀態"""
        self.is_processing = False
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")
        
    def clear_log(self):
        """清除日誌"""
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state="disabled")
        
    def save_log(self):
        """儲存日誌"""
        log_content = self.log_text.get("1.0", tk.END)
        if log_content.strip():
            file_path = filedialog.asksaveasfilename(
                title="儲存日誌",
                defaultextension=".log",
                filetypes=[("日誌檔案", "*.log"), ("文字檔案", "*.txt")]
            )
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(log_content)
                messagebox.showinfo("儲存完成", f"日誌已儲存至：{file_path}")
        
    def show_about(self):
        """顯示關於對話框"""
        about_text = f"""M4A 音檔轉錄工具 - 專業版

功能特色：
• 支援多種音檔格式 (M4A, MP3, WAV, FLAC, AAC)
• 智慧音檔過濾與降噪處理
• 使用 OpenAI Whisper 進行高精度轉錄
• GPT 語意潤飾與繁體中文翻譯
• 批次處理多個檔案
• 可自訂轉錄與翻譯提示詞
• 完整的處理日誌記錄
• 內建結果檢視與編輯功能
• 一鍵複製、匯出轉錄結果

當前 AudioProcessor 預設設定：
• 預設輸出目錄: {self.defaults['text_dir']}
• 預設分割大小: {self.defaults['max_size_mb']}MB
• 音檔過濾: {self.defaults['high_pass_freq']}Hz - {self.defaults['low_pass_freq']}Hz

開發者：Sheng1111
版本：2.1 - 整合API設定與基本設定"""
        messagebox.showinfo("關於", about_text)


class GuiLogHandler(logging.Handler):
    """GUI日誌處理器 - 將 app.py 的日誌顯示在GUI中"""
    
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
        
    def emit(self, record):
        """發送日誌訊息到文字元件"""
        try:
            msg = self.format(record)
            self.text_widget.config(state="normal")
            self.text_widget.insert(tk.END, msg + "\n")
            self.text_widget.see(tk.END)
            self.text_widget.config(state="disabled")
        except Exception:
            pass


def main():
    """主程式入口"""
    root = tk.Tk()
    app = TranscriptionApp(root)
    root.mainloop()


if __name__ == "__main__":
    main() 
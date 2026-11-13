# gunicorn 會自動讀取這個檔案
# 等待 AI 回覆時大部分時間都在「等網路」，所以用多執行緒，讓同時多人使用時不必排隊
worker_class = "gthread"
workers = 1        # 免費方案記憶體只有 512MB，維持 1 個程序
threads = 8        # 同時處理 8 個請求
timeout = 180      # AI 生成可能較久，避免被強制結束

# gunicorn 會自動讀取這個檔案
# AI 生成可能超過預設的 30 秒，放寬到 120 秒，避免 worker 被強制結束
timeout = 120
workers = 1

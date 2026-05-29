from app import create_app

app = create_app()

if __name__ == "__main__":
    # debug=False 关闭自动重载，避免上传文件时 Flask 重启导致 502
    app.run(debug=False, host="0.0.0.0", port=5000)

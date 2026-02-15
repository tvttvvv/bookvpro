from flask import Flask, request, jsonify, send_file
import threading
import uuid
import time
import pandas as pd
import io

app = Flask(__name__)

jobs = {}

# ------------------------
# 더미 검색 함수 (여기에 네이버 API 연결)
# ------------------------
def search_book(keyword):
    time.sleep(0.05)  # 실제 API 호출 대신 대기
    return {
        "keyword": keyword,
        "pc": 100,
        "mobile": 200,
        "total": 300
    }

# ------------------------
# 백그라운드 작업
# ------------------------
def process_job(job_id, book_list):
    results = []
    total = len(book_list)

    for idx, book in enumerate(book_list):
        result = search_book(book)
        results.append(result)

        jobs[job_id]["progress"] = int((idx + 1) / total * 100)

    jobs[job_id]["results"] = results
    jobs[job_id]["status"] = "completed"


# ------------------------
# 메인 페이지 (UI 복구)
# ------------------------
@app.route("/")
def home():
    return """
    <html>
    <head>
        <title>BookVPro</title>
        <style>
            body { font-family: Arial; padding:40px; }
            textarea { width:600px; height:300px; }
            button { padding:10px 20px; font-size:16px; }
            #progress { margin-top:20px; font-size:18px; }
        </style>
    </head>
    <body>

    <h2>BookVPro 대량 검색 시스템</h2>

    <textarea id="books" placeholder="책 제목을 줄바꿈으로 입력하세요"></textarea>
    <br><br>

    <label>
        <input type="checkbox" id="related" checked>
        연관 검색어 포함
    </label>

    <br><br>
    <button onclick="startSearch()">검색 시작</button>

    <div id="progress"></div>

    <script>
    let jobId = null;

    function startSearch(){
        document.getElementById("progress").innerHTML = "검색 시작됨...";

        fetch("/start", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                books: document.getElementById("books").value,
                related: document.getElementById("related").checked
            })
        })
        .then(res => res.json())
        .then(data => {
            jobId = data.job_id;
            checkStatus();
        });
    }

    function checkStatus(){
        fetch("/status/" + jobId)
        .then(res => res.json())
        .then(data => {
            document.getElementById("progress").innerHTML =
                "진행률: " + data.progress + "%";

            if(data.status !== "completed"){
                setTimeout(checkStatus, 2000);
            } else {
                document.getElementById("progress").innerHTML +=
                "<br><br><a href='/download/" + jobId + "'>엑셀 다운로드</a>";
            }
        });
    }
    </script>

    </body>
    </html>
    """


# ------------------------
# 작업 시작
# ------------------------
@app.route("/start", methods=["POST"])
def start():
    data = request.json
    books = data["books"].splitlines()
    books = [b.strip() for b in books if b.strip()]

    job_id = str(uuid.uuid4())

    jobs[job_id] = {
        "status": "running",
        "progress": 0,
        "results": []
    }

    thread = threading.Thread(target=process_job, args=(job_id, books))
    thread.start()

    return jsonify({"job_id": job_id})


# ------------------------
# 상태 확인
# ------------------------
@app.route("/status/<job_id>")
def status(job_id):
    return jsonify(jobs[job_id])


# ------------------------
# 엑셀 다운로드
# ------------------------
@app.route("/download/<job_id>")
def download(job_id):
    df = pd.DataFrame(jobs[job_id]["results"])

    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="result.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

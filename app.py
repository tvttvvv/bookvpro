import os
import time
import uuid
import threading
import hashlib
import hmac
import base64
import requests
import pandas as pd
from flask import Flask, request, jsonify, send_file, render_template_string
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

ACCESS_KEY = os.environ.get("ACCESS_KEY")
SECRET_KEY = os.environ.get("SECRET_KEY")
CUSTOMER_ID = os.environ.get("CUSTOMER_ID")

BASE_URL = "https://api.searchad.naver.com"

app = Flask(__name__)
jobs = {}

# ------------------------
# 서명
# ------------------------
def generate_signature(timestamp, method, uri):
    message = f"{timestamp}.{method}.{uri}"
    signature = hmac.new(
        SECRET_KEY.encode(),
        message.encode(),
        hashlib.sha256
    ).digest()
    return base64.b64encode(signature).decode()

# ------------------------
# 검색
# ------------------------
def search_keyword(keyword):

    uri = "/keywordstool"
    method = "GET"
    timestamp = str(int(time.time() * 1000))
    signature = generate_signature(timestamp, method, uri)

    headers = {
        "X-Timestamp": timestamp,
        "X-API-KEY": ACCESS_KEY,
        "X-Customer": CUSTOMER_ID,
        "X-Signature": signature,
    }

    params = {"hintKeywords": keyword, "showDetail": 1}

    try:
        r = requests.get(BASE_URL + uri, headers=headers, params=params, timeout=5)
        if r.status_code != 200:
            return {"keyword": keyword, "total": 0}

        data = r.json().get("keywordList", [])
        if not data:
            return {"keyword": keyword, "total": 0}

        pc = int(str(data[0]["monthlyPcQcCnt"]).replace(",", "").replace("< 10","0"))
        mobile = int(str(data[0]["monthlyMobileQcCnt"]).replace(",", "").replace("< 10","0"))

        return {"keyword": keyword, "total": pc + mobile}

    except:
        return {"keyword": keyword, "total": 0}

# ------------------------
# 배치 처리 (100개씩)
# ------------------------
def process_job(job_id, books):

    batch_size = 100
    total = len(books)
    completed = 0

    results = []

    for i in range(0, total, batch_size):

        batch = books[i:i+batch_size]

        with ThreadPoolExecutor(max_workers=3) as executor:
            batch_results = list(executor.map(search_keyword, batch))

        results.extend(batch_results)

        completed += len(batch)
        jobs[job_id]["progress"] = int((completed / total) * 100)

        time.sleep(0.2)  # API 보호

    jobs[job_id]["results"] = results
    jobs[job_id]["status"] = "completed"

# ------------------------
# 시작
# ------------------------
@app.route("/start", methods=["POST"])
def start():

    books = [b.strip() for b in request.json["books"].split("\n") if b.strip()]

    job_id = str(uuid.uuid4())

    jobs[job_id] = {
        "status": "processing",
        "progress": 0,
        "results": []
    }

    threading.Thread(target=process_job, args=(job_id, books)).start()

    return jsonify({"job_id": job_id})

# ------------------------
# 상태
# ------------------------
@app.route("/status/<job_id>")
def status(job_id):
    return jsonify(jobs.get(job_id, {}))

# ------------------------
# 다운로드
# ------------------------
@app.route("/download/<job_id>")
def download(job_id):

    df = pd.DataFrame(jobs[job_id]["results"])

    output = BytesIO()
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

@app.route("/")
def home():
    return """
    <h2>BookVPro 대량 검색 시스템</h2>
    <form id="form">
        <textarea id="books" rows="15" cols="60" placeholder="책 제목을 줄바꿈으로 입력하세요"></textarea><br><br>
        <button type="button" onclick="startSearch()">검색 시작</button>
    </form>
    <br>
    <div id="progress"></div>

    <script>
    let jobId = null;

    function startSearch(){
        fetch("/start", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({books: document.getElementById("books").value})
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
                "<br><a href='/download/" + jobId + "'>엑셀 다운로드</a>";
            }
        });
    }
    </script>
    """

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
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed

ACCESS_KEY = os.environ.get("ACCESS_KEY")
SECRET_KEY = os.environ.get("SECRET_KEY")
CUSTOMER_ID = os.environ.get("CUSTOMER_ID")

BASE_URL = "https://api.searchad.naver.com"

app = Flask(__name__)

# 작업 상태 저장소 (메모리)
jobs = {}

# -----------------------------
# 서명 생성
# -----------------------------
def generate_signature(timestamp, method, uri, secret_key):
    message = f"{timestamp}.{method}.{uri}"
    signature = hmac.new(
        secret_key.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    ).digest()
    return base64.b64encode(signature).decode()

# -----------------------------
# 단일 키워드 검색
# -----------------------------
def search_keyword(keyword):

    uri = "/keywordstool"
    method = "GET"
    timestamp = str(int(time.time() * 1000))

    signature = generate_signature(timestamp, method, uri, SECRET_KEY)

    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "X-Timestamp": timestamp,
        "X-API-KEY": ACCESS_KEY,
        "X-Customer": CUSTOMER_ID,
        "X-Signature": signature,
    }

    params = {
        "hintKeywords": keyword,
        "showDetail": 1
    }

    try:
        response = requests.get(BASE_URL + uri, headers=headers, params=params, timeout=7)

        if response.status_code != 200:
            return {"keyword": keyword, "pc": 0, "mobile": 0, "total": 0}

        data = response.json().get("keywordList", [])
        if not data:
            return {"keyword": keyword, "pc": 0, "mobile": 0, "total": 0}

        item = data[0]

        def safe_convert(value):
            if isinstance(value, str):
                if "<" in value:
                    return 0
                return int(value.replace(",", ""))
            return int(value)

        pc = safe_convert(item["monthlyPcQcCnt"])
        mobile = safe_convert(item["monthlyMobileQcCnt"])

        return {
            "keyword": keyword,
            "pc": pc,
            "mobile": mobile,
            "total": pc + mobile
        }

    except:
        return {"keyword": keyword, "pc": 0, "mobile": 0, "total": 0}

# -----------------------------
# 백그라운드 작업
# -----------------------------
def process_job(job_id, books):

    total = len(books)
    results = [None] * total

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_map = {
            executor.submit(search_keyword, books[i]): i
            for i in range(total)
        }

        completed = 0
        for future in as_completed(future_map):
            index = future_map[future]
            results[index] = future.result()
            completed += 1
            jobs[job_id]["progress"] = int((completed / total) * 100)

    jobs[job_id]["results"] = results
    jobs[job_id]["status"] = "completed"

# -----------------------------
# 메인 페이지
# -----------------------------
@app.route("/")
def home():
    return render_template_string("""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>BookVPro</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">
<div class="container mt-5">
<h2 class="mb-4 text-center">📚 BookVPro 대량 검색 시스템</h2>

<form id="searchForm">
<textarea name="books" class="form-control mb-3" rows="10"
placeholder="책 제목을 한 줄에 하나씩 입력하세요 (최대 1000개)"></textarea>

<button type="submit" class="btn btn-primary w-100">검색 시작</button>
</form>

<div class="mt-4">
<div class="progress">
<div id="progressBar" class="progress-bar" role="progressbar" style="width: 0%">0%</div>
</div>
</div>

<div id="downloadSection" class="mt-3" style="display:none;">
<a id="downloadLink" class="btn btn-success">엑셀 다운로드</a>
</div>

</div>

<script>
document.getElementById("searchForm").addEventListener("submit", function(e){
e.preventDefault();

fetch("/start", {
method: "POST",
headers: {"Content-Type":"application/json"},
body: JSON.stringify({books: document.querySelector("textarea").value})
})
.then(res => res.json())
.then(data => {
let jobId = data.job_id;
checkStatus(jobId);
});
});

function checkStatus(jobId){
fetch("/status/" + jobId)
.then(res => res.json())
.then(data => {
let percent = data.progress;
document.getElementById("progressBar").style.width = percent + "%";
document.getElementById("progressBar").innerText = percent + "%";

if(data.status === "completed"){
document.getElementById("downloadSection").style.display = "block";
document.getElementById("downloadLink").href = "/download/" + jobId;
}else{
setTimeout(function(){checkStatus(jobId)}, 2000);
}
});
}
</script>
</body>
</html>
""")

# -----------------------------
# 작업 시작
# -----------------------------
@app.route("/start", methods=["POST"])
def start_job():
    data = request.json
    books = [b.strip() for b in data["books"].split("\n") if b.strip()]

    job_id = str(uuid.uuid4())

    jobs[job_id] = {
        "status": "processing",
        "progress": 0,
        "results": []
    }

    thread = threading.Thread(target=process_job, args=(job_id, books))
    thread.start()

    return jsonify({"job_id": job_id})

# -----------------------------
# 상태 확인
# -----------------------------
@app.route("/status/<job_id>")
def check_status(job_id):
    return jsonify(jobs.get(job_id, {"status":"unknown","progress":0}))

# -----------------------------
# 엑셀 다운로드
# -----------------------------
@app.route("/download/<job_id>")
def download(job_id):
    data = jobs.get(job_id, {}).get("results", [])
    df = pd.DataFrame(data)

    output = BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="bookvpro_result.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

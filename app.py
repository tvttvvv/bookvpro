from flask import Flask, request, jsonify, send_file
import requests
import hashlib
import hmac
import base64
import time
import os
import threading
import uuid
import pandas as pd
import io

app = Flask(__name__)
jobs = {}

ACCESS_KEY = os.environ.get("ACCESS_KEY")
SECRET_KEY = os.environ.get("SECRET_KEY")
CUSTOMER_ID = os.environ.get("CUSTOMER_ID")

# -----------------------------
# 네이버 서명 생성
# -----------------------------
def generate_signature(timestamp, method, uri):
    message = f"{timestamp}.{method}.{uri}"
    hash = hmac.new(
        SECRET_KEY.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256
    )
    return base64.b64encode(hash.digest()).decode()

# -----------------------------
# 네이버 검색 API
# -----------------------------
def search_book(keyword):
    timestamp = str(int(time.time() * 1000))
    method = "GET"
    uri = "/keywordstool"

    signature = generate_signature(timestamp, method, uri)

    headers = {
        "X-Timestamp": timestamp,
        "X-API-KEY": ACCESS_KEY,
        "X-Customer": CUSTOMER_ID,
        "X-Signature": signature,
    }

    params = {
        "hintKeywords": keyword,
        "showDetail": 1
    }

    url = "https://api.naver.com" + uri
    response = requests.get(url, headers=headers, params=params)

    if response.status_code != 200:
        return {"keyword": keyword, "pc": 0, "mobile": 0, "total": 0}

    data = response.json()

    if "keywordList" not in data or not data["keywordList"]:
        return {"keyword": keyword, "pc": 0, "mobile": 0, "total": 0}

    item = data["keywordList"][0]

    pc = item.get("monthlyPcQcCnt", 0)
    mobile = item.get("monthlyMobileQcCnt", 0)

    if pc == "< 10": pc = 0
    if mobile == "< 10": mobile = 0

    pc = int(pc)
    mobile = int(mobile)

    return {
        "keyword": keyword,
        "pc": pc,
        "mobile": mobile,
        "total": pc + mobile
    }

# -----------------------------
# 백그라운드 처리 (대량 대응)
# -----------------------------
def process_job(job_id, book_list):
    results = []
    total = len(book_list)

    for idx, book in enumerate(book_list):
        result = search_book(book)
        results.append(result)
        jobs[job_id]["progress"] = int((idx + 1) / total * 100)

    jobs[job_id]["results"] = results
    jobs[job_id]["status"] = "completed"

# -----------------------------
# 메인 UI (도표 복구)
# -----------------------------
@app.route("/")
def home():
    return """
    <html>
    <head>
    <title>BookVPro</title>
    <style>
    body {font-family:Arial;padding:40px;}
    textarea {width:600px;height:250px;}
    table {border-collapse:collapse;margin-top:20px;min-width:1100px;}
    th,td {border:1px solid #ccc;padding:8px;text-align:center;}
    th {background:#222;color:#fff;}
    #table-container {overflow-x:auto;}
    button {padding:10px 20px;font-size:16px;}
    </style>
    </head>
    <body>

    <h2>BookVPro 검색 시스템</h2>

    <textarea id="books" placeholder="책 제목을 줄바꿈으로 입력하세요"></textarea><br><br>

    <label>
        <input type="checkbox" id="related" checked>
        연관검색어 포함
    </label>

    <br><br>
    <button onclick="startSearch()">검색 시작</button>

    <div id="progress" style="margin-top:20px;font-size:18px;"></div>

    <div id="table-container">
        <table id="result-table"></table>
    </div>

    <script>
    let jobId = null;

    function startSearch(){
        document.getElementById("progress").innerHTML = "🔄 검색 진행중...";
        document.getElementById("result-table").innerHTML = "";

        fetch("/start",{
            method:"POST",
            headers:{"Content-Type":"application/json"},
            body:JSON.stringify({
                books:document.getElementById("books").value,
                related:document.getElementById("related").checked
            })
        })
        .then(res=>res.json())
        .then(data=>{
            jobId=data.job_id;
            checkStatus();
        });
    }

    function checkStatus(){
        fetch("/status/"+jobId)
        .then(res=>res.json())
        .then(data=>{
            document.getElementById("progress").innerHTML="진행률: "+data.progress+"%";

            if(data.status!=="completed"){
                setTimeout(checkStatus,2000);
            } else {
                loadTable(data.results);
                document.getElementById("progress").innerHTML +=
                "<br><br><a href='/download/"+jobId+"'>엑셀 다운로드</a>";
            }
        });
    }

    function loadTable(results){
        let table=document.getElementById("result-table");
        let html="<tr><th>선택</th><th>책 제목</th><th>PC</th><th>모바일</th><th>총합</th></tr>";

        results.forEach(r=>{
            html+=`<tr>
                <td><input type='checkbox' checked></td>
                <td>${r.keyword}</td>
                <td>${r.pc}</td>
                <td>${r.mobile}</td>
                <td>${r.total}</td>
            </tr>`;
        });

        table.innerHTML=html;
    }
    </script>

    </body>
    </html>
    """

# -----------------------------
# 작업 시작
# -----------------------------
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

    threading.Thread(target=process_job, args=(job_id, books)).start()
    return jsonify({"job_id": job_id})

# -----------------------------
# 상태 확인
# -----------------------------
@app.route("/status/<job_id>")
def status(job_id):
    return jsonify(jobs[job_id])

# -----------------------------
# 엑셀 다운로드
# -----------------------------
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

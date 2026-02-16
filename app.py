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
        return {
            "keyword": keyword,
            "pc": 0,
            "mobile": 0,
            "total": 0,
            "related": []
        }

    data = response.json()

    if "keywordList" not in data or not data["keywordList"]:
        return {
            "keyword": keyword,
            "pc": 0,
            "mobile": 0,
            "total": 0,
            "related": []
        }

    first = data["keywordList"][0]

    pc = first.get("monthlyPcQcCnt", 0)
    mobile = first.get("monthlyMobileQcCnt", 0)

    if pc == "< 10":
        pc = 0
    if mobile == "< 10":
        mobile = 0

    pc = int(pc)
    mobile = int(mobile)

    related = []
    for item in data["keywordList"][:10]:
        if item.get("relKeyword") and item["relKeyword"] != keyword:
            related.append(item["relKeyword"])

    return {
        "keyword": keyword,
        "pc": pc,
        "mobile": mobile,
        "total": pc + mobile,
        "related": related
    }


# -----------------------------
# 백그라운드 처리
# -----------------------------
def process_job(job_id, book_list):
    results = []
    total = len(book_list)

    for idx, book in enumerate(book_list):

        main_result = search_book(book)

        detailed_related = []
        for rel in main_result["related"]:
            rel_result = search_book(rel)
            detailed_related.append(rel_result)

        main_result["related_detail"] = detailed_related

        results.append(main_result)
        jobs[job_id]["progress"] = int((idx + 1) / total * 100)

    jobs[job_id]["results"] = results
    jobs[job_id]["status"] = "completed"


# -----------------------------
# UI
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
    table {border-collapse:collapse;margin-top:20px;min-width:1200px;}
    th,td {border:1px solid #ccc;padding:8px;text-align:center;}
    th {background:#222;color:#fff;}
    #table-container {overflow-x:auto;}
    .related-row {background:#f7f7f7;}
    select,button {padding:6px;}
    </style>
    </head>
    <body>

    <h2>BookVPro 검색 시스템</h2>

    <textarea id="books" placeholder="책 제목을 줄바꿈으로 입력하세요"></textarea><br><br>
    <button onclick="startSearch()">검색 시작</button>

    <div id="progress" style="margin-top:20px;font-size:18px;"></div>

    <div style="margin-top:20px; display:flex; gap:30px; align-items:center;">
        <div>
            <label>정렬: </label>
            <select id="sortOption" onchange="applyFilters()">
                <option value="original">원본 순서</option>
                <option value="desc">조회수 높은순</option>
                <option value="asc">조회수 낮은순</option>
            </select>
        </div>

        <div>
            <label>연관검색어: </label>
            <select id="relatedOption" onchange="applyFilters()">
                <option value="original">원본</option>
                <option value="relatedOnly">연관검색어만</option>
                <option value="all">전체</option>
            </select>
        </div>
    </div>

    <div id="table-container">
        <table id="result-table"></table>
    </div>

    <script>

    let jobId = null;
    let originalResults = [];

    function startSearch(){
        document.getElementById("progress").innerHTML = "검색 진행중...";
        document.getElementById("result-table").innerHTML = "";

        fetch("/start",{
            method:"POST",
            headers:{"Content-Type":"application/json"},
            body:JSON.stringify({
                books:document.getElementById("books").value
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
                originalResults = data.results;
                applyFilters();
                document.getElementById("progress").innerHTML +=
                "<br><br><a href='/download/"+jobId+"'>엑셀 다운로드</a>";
            }
        });
    }

    function applyFilters(){

        let sortOption = document.getElementById("sortOption").value;
        let relatedOption = document.getElementById("relatedOption").value;

        let filtered = [...originalResults];

        if(sortOption === "desc"){
            filtered.sort((a,b)=> b.total - a.total);
        }
        else if(sortOption === "asc"){
            filtered.sort((a,b)=> a.total - b.total);
        }

        loadTable(filtered, relatedOption, sortOption);
    }

    function loadTable(results, relatedOption="original", sortOption="original"){

        let table=document.getElementById("result-table");
        let html="<tr><th>구분</th><th>키워드</th><th>PC</th><th>모바일</th><th>총합</th></tr>";

        if(relatedOption === "relatedOnly"){

            let allRelated = [];

            results.forEach(r=>{
                if(r.related_detail){
                    r.related_detail.forEach(rel=>{
                        allRelated.push(rel);
                    });
                }
            });

            if(sortOption === "desc"){
                allRelated.sort((a,b)=> b.total - a.total);
            }
            else if(sortOption === "asc"){
                allRelated.sort((a,b)=> a.total - b.total);
            }

            allRelated.forEach(rel=>{
                html+=`<tr class="related-row">
                    <td>연관</td>
                    <td>${rel.keyword}</td>
                    <td>${rel.pc}</td>
                    <td>${rel.mobile}</td>
                    <td>${rel.total}</td>
                </tr>`;
            });

        }
        else{

            results.forEach(r=>{

                html+=`<tr>
                    <td>도서</td>
                    <td><b>${r.keyword}</b></td>
                    <td>${r.pc}</td>
                    <td>${r.mobile}</td>
                    <td>${r.total}</td>
                </tr>`;

                if(relatedOption === "all" && r.related_detail){
                    r.related_detail.forEach(rel=>{
                        html+=`<tr class="related-row">
                            <td>연관</td>
                            <td>↳ ${rel.keyword}</td>
                            <td>${rel.pc}</td>
                            <td>${rel.mobile}</td>
                            <td>${rel.total}</td>
                        </tr>`;
                    });
                }

            });
        }

        table.innerHTML=html;
    }

    </script>

    </body>
    </html>
    """


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


@app.route("/status/<job_id>")
def status(job_id):
    return jsonify(jobs[job_id])


@app.route("/download/<job_id>")
def download(job_id):
    rows = []
    for r in jobs[job_id]["results"]:
        rows.append(r)
        for rel in r.get("related_detail", []):
            rows.append(rel)

    df = pd.DataFrame(rows)
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
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

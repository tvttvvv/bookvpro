from flask import Flask, request, jsonify, send_file
import threading
import uuid
import time
import pandas as pd
import io

app = Flask(__name__)
jobs = {}

# ------------------------
# 더미 검색 (여기에 네이버 API 연결)
# ------------------------
def search_book(keyword):
    time.sleep(0.02)
    return {
        "keyword": keyword,
        "pc": 120,
        "mobile": 340,
        "total": 460
    }

# ------------------------
# 백그라운드 처리
# ------------------------
def process_job(job_id, book_list):
    results = []
    total = len(book_list)

    for idx, book in enumerate(book_list):
        result = search_book(book)
        results.append(result)
        jobs[job_id]["progress"] = int((idx+1)/total*100)

    jobs[job_id]["results"] = results
    jobs[job_id]["status"] = "completed"


# ------------------------
# 메인 페이지 (도표 복구)
# ------------------------
@app.route("/")
def home():
    return """
    <html>
    <head>
    <style>
    body {font-family:Arial;padding:40px;}
    textarea {width:600px;height:250px;}
    table {border-collapse:collapse; margin-top:20px; min-width:1000px;}
    th,td {border:1px solid #ddd;padding:8px;text-align:center;}
    th {background:#333;color:#fff;}
    #table-container {overflow-x:auto;}
    </style>
    </head>
    <body>

    <h2>BookVPro 검색 시스템</h2>

    <textarea id="books" placeholder="책 제목 줄바꿈 입력"></textarea><br><br>

    <label>
        <input type="checkbox" id="related" checked>
        연관검색어 표시
    </label>

    <br><br>
    <button onclick="startSearch()">검색 시작</button>

    <div id="progress"></div>

    <div id="table-container">
        <table id="result-table"></table>
    </div>

    <script>
    let jobId = null;

    function startSearch(){
        document.getElementById("progress").innerHTML = "🔄 로딩중...";
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
                "<br><a href='/download/"+jobId+"'>엑셀 다운로드</a>";
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


@app.route("/start",methods=["POST"])
def start():
    data=request.json
    books=data["books"].splitlines()
    books=[b.strip() for b in books if b.strip()]

    job_id=str(uuid.uuid4())

    jobs[job_id]={
        "status":"running",
        "progress":0,
        "results":[]
    }

    threading.Thread(target=process_job,args=(job_id,books)).start()
    return jsonify({"job_id":job_id})


@app.route("/status/<job_id>")
def status(job_id):
    return jsonify(jobs[job_id])


@app.route("/download/<job_id>")
def download(job_id):
    df=pd.DataFrame(jobs[job_id]["results"])
    output=io.BytesIO()
    df.to_excel(output,index=False)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="result.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


if __name__=="__main__":
    app.run(host="0.0.0.0",port=8080)

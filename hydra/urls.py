"""
URL configuration for Plato.
"""
from django.http import HttpResponse
from django.urls import path, include


INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Plato Console</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:monospace;background:#0d1117;color:#c9d1d9;padding:20px}
h1{color:#58a6ff;font-size:20px;margin-bottom:4px}
.sub{color:#8b949e;font-size:12px;margin-bottom:20px}
.row{display:flex;gap:20px;flex-wrap:wrap}
.col{flex:1;min-width:300px;max-width:500px}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px;margin-bottom:16px}
.card h3{font-size:14px;color:#58a6ff;margin-bottom:12px}
input,select,button{font-family:monospace;font-size:13px;padding:6px 10px;border:1px solid #30363d;border-radius:6px;background:#0d1117;color:#c9d1d9;margin:4px 0;width:100%}
button{background:#238636;color:#fff;border:none;cursor:pointer;width:auto;padding:6px 16px}
button:hover{background:#2ea043}
button.danger{background:#da3633}
button.danger:hover{background:#f85149}
.result{background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:10px;margin-top:8px;max-height:300px;overflow:auto;font-size:12px;white-space:pre-wrap;word-break:break-all}
.green{color:#3fb950}
.red{color:#f85149}
.gray{color:#8b949e}
table{width:100%;border-collapse:collapse;font-size:12px;margin-top:8px}
td,th{border:1px solid #30363d;padding:4px 8px;text-align:left}
th{background:#161b22;color:#58a6ff}
.badge{display:inline-block;padding:1px 6px;border-radius:10px;font-size:10px;margin:2px}
.badge-ok{background:#033a16;color:#3fb950}
.label{font-size:11px;color:#8b949e;margin-bottom:2px;display:block}
.inline{display:flex;gap:8px;align-items:end}
.inline>*{flex:1}
</style>
</head>
<body>
<h1>🏛️ Plato Console</h1>
<p class="sub">API Playground — 建表、插数据、查数据、定时任务</p>

<div class="row">
<div class="col">

<div class="card">
<h3>1️⃣ 创建动态表</h3>
<label class="label">表名（英文）</label>
<input id="tbl_name" placeholder="sales_leads" value="my_table">
<label class="label">列定义（JSON）</label>
<input id="tbl_cols" placeholder='[{"name":"col1","col_type":"string"}]' value='[{"name":"company","col_type":"string","nullable":false},{"name":"revenue","col_type":"decimal","default":0},{"name":"stage","col_type":"string","default":"lead"}]'>
<button onclick="createTable()">创建表</button>
<pre class="result" id="r_create">等待操作...</pre>
</div>

<div class="card">
<h3>2️⃣ 插入数据</h3>
<label class="label">表名</label>
<input id="ins_table" placeholder="表名" value="my_table">
<label class="label">行数据（JSON）</label>
<input id="ins_data" placeholder='{"col1":"value"}' value='{"company":"Acme Corp","revenue":150000,"stage":"negotiation"}'>
<button onclick="insertRow()">插入行</button>
<pre class="result" id="r_insert">等待操作...</pre>
</div>

<div class="card">
<h3>3️⃣ 添加列</h3>
<label class="label">表名</label>
<input id="col_table" value="my_table">
<label class="label">列定义</label>
<input id="col_def" placeholder='{"name":"new_col","col_type":"integer"}' value='{"name":"employees","col_type":"integer","default":0}'>
<button onclick="addColumn()">添加列</button>
<pre class="result" id="r_column">等待操作...</pre>
</div>

</div>
<div class="col">

<div class="card">
<h3>4️⃣ 查询数据</h3>
<label class="label">表名</label>
<input id="qry_table" value="my_table">
<div class="inline">
<button onclick="queryRows()">查询所有行</button>
<button onclick="listTables()">列出所有表</button>
</div>
<pre class="result" id="r_query">等待操作...</pre>
</div>

<div class="card">
<h3>5️⃣ 定时任务</h3>
<label class="label">任务名</label>
<input id="sch_name" value="Daily Validate">
<label class="label">表名</label>
<input id="sch_table" value="my_table">
<label class="label">Cron 表达式（分 时）</label>
<div class="inline">
<input id="sch_min" value="0" placeholder="分">
<input id="sch_hour" value="2" placeholder="时">
</div>
<button onclick="createSchedule()">创建定时任务</button>
<button onclick="listSchedules()" style="margin-top:4px">列出所有任务</button>
<pre class="result" id="r_schedule">等待操作...</pre>
</div>

<div class="card">
<h3>🏆 系统状态</h3>
<p><span class="badge badge-ok">✅</span> 动态Schema <span class="badge badge-ok">✅</span> Yjs协同 <span class="badge badge-ok">✅</span> Rust引擎</p>
<p><span class="badge badge-ok">✅</span> ClickHouse <span class="badge badge-ok">✅</span> Celery调度</p>
<p class="gray" style="margin-top:8px;font-size:11px">Django 6 · PG 16 · Redis 7 · CH 24.8 · Rust/PyO3</p>
</div>

</div>
</div>

<script>
async function api(method,url,body){
  try{
    let opts={method,headers:{"Content-Type":"application/json"}};
    if(body)opts.body=JSON.stringify(body);
    let r=await fetch(url,opts);
    let d=await r.json();
    return {ok:r.ok,status:r.status,data:d};
  }catch(e){return {ok:false,error:e.message}}
}

async function createTable(){
  let name=document.getElementById("tbl_name").value;
  let cols;
  try{cols=JSON.parse(document.getElementById("tbl_cols").value)}catch(e){document.getElementById("r_create").innerHTML='<span class="red">JSON格式错误</span>';return}
  let r=await api("POST","/api/tables/",{name,display_name:name,columns:cols});
  document.getElementById("r_create").innerHTML=JSON.stringify(r.data,null,2);
}

async function insertRow(){
  let t=document.getElementById("ins_table").value;
  let d;
  try{d=JSON.parse(document.getElementById("ins_data").value)}catch(e){document.getElementById("r_insert").innerHTML='<span class="red">JSON格式错误</span>';return}
  let r=await api("POST","/api/tables/"+t+"/rows/",d);
  document.getElementById("r_insert").innerHTML=JSON.stringify(r.data,null,2);
}

async function addColumn(){
  let t=document.getElementById("col_table").value;
  let d;
  try{d=JSON.parse(document.getElementById("col_def").value)}catch(e){document.getElementById("r_column").innerHTML='<span class="red">JSON格式错误</span>';return}
  let r=await api("POST","/api/tables/"+t+"/columns/",d);
  document.getElementById("r_column").innerHTML=JSON.stringify(r.data,null,2);
}

async function queryRows(){
  let t=document.getElementById("qry_table").value;
  let r=await api("GET","/api/tables/"+t+"/rows/list/?limit=20");
  let out=r.data;
  if(out.rows&&out.rows.length>0){
    let cols=Object.keys(out.rows[0]).filter(k=>!k.startsWith("_"));
    let h="<table><tr>"+cols.map(c=>"<th>"+c+"</th>").join("")+"</tr>";
    h+=out.rows.map(row=>"<tr>"+cols.map(c=>"<td>"+(row[c]??"")+"</td>").join("")+"</tr>").join("");
    h+="</table><br><span class='gray'>共 "+out.total+" 行</span>";
    document.getElementById("r_query").innerHTML=h;
  }else{
    document.getElementById("r_query").innerHTML=JSON.stringify(out,null,2);
  }
}

async function listTables(){
  let r=await api("GET","/api/tables/list/");
  let out=r.data;
  if(out.tables){
    let h="";
    out.tables.forEach(t=>{
      h+="<b>"+t.name+"</b> ("+t.columns.length+" 列): ";
      h+=t.columns.map(c=>c.name+"("+c.type+")").join(", ");
      h+="\n";
    });
    document.getElementById("r_query").innerHTML=h||"没有动态表";
  }
}

async function createSchedule(){
  let r=await api("POST","/api/tasks/schedules/create/",{
    name:document.getElementById("sch_name").value,
    task_type:"validate_table",
    table_name:document.getElementById("sch_table").value,
    schedule_type:"crontab",
    schedule_config:{minute:document.getElementById("sch_min").value,hour:document.getElementById("sch_hour").value}
  });
  document.getElementById("r_schedule").innerHTML=JSON.stringify(r.data,null,2);
}

async function listSchedules(){
  let r=await api("GET","/api/tasks/schedules/");
  document.getElementById("r_schedule").innerHTML=JSON.stringify(r.data,null,2);
}
</script>
</body>
</html>"""


def index(request):
    return HttpResponse(INDEX_HTML)


urlpatterns = [
    path("", index, name="index"),
    path("api/", include("apps.dynamic_models.urls")),
    path("api/tenants/", include("apps.tenants.urls")),
    path("api/graphql", include("apps.dynamic_models.graphql_urls")),
]

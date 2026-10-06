#!/usr/bin/env python3
"""bbwide.py -- wide sortable stats table for FPS Baseball Pro '98.

usage: python3 bbwide.py [--snap DIR] [--port 8099]
       python3 bbwide.py [--snap DIR] --dump bat|pit SCOPE [MIN]
"""
import sys, os, json
sys.path.insert(0, '/home/will/bbpro98/work')
import bbstats
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

DEFAULT_SNAP = '/home/will/.bbpro98_prefix/drive_c/Sierra/BBPRO_98'
SNAP = DEFAULT_SNAP
USAGE = ('usage: bbwide.py [--snap DIR] [--port 8099]\n'
         '       bbwide.py [--snap DIR] --dump bat|pit SCOPE [MIN]\n')

BAT_COLS = ['Name', 'G', 'AB', 'R', 'H', '2B', '3B', 'HR', 'RBI', 'BB', 'SO', 'SB', 'CS',
            'AVG', 'OBP', 'SLG', 'OPS', 'ISO', 'BB%', 'K%', 'BB/K', 'wOBA', 'OPS+', 'oWAR~']
PIT_COLS = ['Name', 'W', 'L', 'SV', 'IP', 'H', 'R', 'ER', 'HR', 'BB', 'SO',
            'ERA', 'WHIP', 'K/9', 'BB/9', 'HR/9', 'H/9', 'K/BB', 'FIP', 'ERA+', 'pWAR~']


def div(a, b):
    return None if not b else a / b

def r3(x):
    return None if x is None else round(x, 3)

def r1(x):
    return None if x is None else round(x, 1)

def get_names(snap):
    try:
        return bbstats.names(os.path.join(snap, 'Assn', 'MLBPA97.PYR'))
    except Exception:
        return {}


def bat_table(snap, scope, minv):
    bat, _pit = bbstats.lines(snap, scope)
    bat = {k: v for k, v in bat.items() if k >= 100}  # ids < 100 are team/league total rows
    nm = get_names(snap)
    AB = S = D = T = HR = BB = PA = H = TB = 0
    for c in bat.values():
        if len(c) < 16:
            continue
        AB += c[0]; S += c[1]; D += c[2]; T += c[3]; HR += c[4]; BB += c[6]
        PA += c[0] + c[6]; H += c[1] + c[2] + c[3] + c[4]
        TB += c[1] + 2 * c[2] + 3 * c[3] + 4 * c[4]
    lgOBP = div(H + BB, PA)
    lgSLG = div(TB, AB)
    lgwOBA = div(0.69 * BB + 0.88 * S + 1.24 * D + 1.56 * T + 2.0 * HR, PA)
    rows = []
    for pid, c in bat.items():
        if len(c) < 16:
            continue
        ab, s, d, trip, hr, rbi, bb, so = c[0], c[1], c[2], c[3], c[4], c[5], c[6], c[7]
        if ab < minv:
            continue
        h = s + d + trip + hr
        tb = s + 2 * d + 3 * trip + 4 * hr
        pa = ab + bb
        avg = div(h, ab)
        obp = div(h + bb, pa)
        slg = div(tb, ab)
        ops = None if (obp is None or slg is None) else obp + slg
        iso = None if (slg is None or avg is None) else slg - avg
        woba = div(0.69 * bb + 0.88 * s + 1.24 * d + 1.56 * trip + 2.0 * hr, pa)
        ops_plus = None
        if obp is not None and slg is not None and lgOBP and lgSLG:
            ops_plus = round(100 * (obp / lgOBP + slg / lgSLG - 1))
        owar = None
        if woba is not None and lgwOBA:
            batruns = (woba - lgwOBA) / 1.2 * pa
            owar = (batruns + 20 * pa / 600 + 0.2 * c[14] - 0.4 * c[15]) / 10
        rows.append([nm.get(pid, str(pid)), c[12], ab, c[13], h, d, trip, hr, rbi, bb, so,
                     c[14], c[15], r3(avg), r3(obp), r3(slg), r3(ops), r3(iso),
                     r3(div(bb, pa)), r3(div(so, pa)), r3(div(bb, so)), r3(woba),
                     ops_plus, r1(owar)])
    return rows


def pit_table(snap, scope, minv):
    _bat, pit = bbstats.lines(snap, scope)
    pit = {k: v for k, v in pit.items() if k >= 100}  # ids < 100 are team/league total rows
    nm = get_names(snap)
    OUTS = ER = HR = BB = SO = 0
    for c in pit.values():
        if len(c) < 27:
            continue
        OUTS += c[18]; ER += c[26]; HR += c[4]; BB += c[6]; SO += c[7]
    lgERA = div(27 * ER, OUTS)
    fipc = None
    if lgERA is not None and OUTS:
        fipc = lgERA - (13 * HR + 3 * BB - 2 * SO) / (OUTS / 3)
    rows = []
    for pid, c in pit.items():
        if len(c) < 27:
            continue
        os_, od, ot, hra, bba, so = c[1], c[2], c[3], c[4], c[6], c[7]
        r, outs, w, l, sv, er = c[13], c[18], c[20], c[21], c[22], c[26]
        if outs < minv:
            continue
        ha = os_ + od + ot + hra
        ip = outs / 3
        ipd = outs // 3 + (outs % 3) / 10
        era = div(27 * er, outs)
        fip = None
        if fipc is not None and ip:
            fip = (13 * hra + 3 * bba - 2 * so) / ip + fipc
        pwar = None
        if fip is not None and lgERA is not None:
            pwar = ((lgERA - fip) * ip / 9 + 20 * ip / 200) / 10
        erap = None
        if era and lgERA is not None:
            erap = round(100 * lgERA / era)
        rows.append([nm.get(pid, str(pid)), w, l, sv, ipd, ha, r, er, hra, bba, so,
                     r3(era), r3(div(3 * (ha + bba), outs)), r3(div(27 * so, outs)),
                     r3(div(27 * bba, outs)), r3(div(27 * hra, outs)),
                     r3(div(27 * ha, outs)), r3(div(so, bba)), r3(fip), erap, r1(pwar)])
    return rows


def scopes_available(snap):
    out = []
    for s in (0, 1, 2):
        try:
            b, p = bbstats.lines(snap, s)
        except Exception:
            continue
        if b or p:
            out.append(s)
    return out


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BBPRO '98 Wide Stats</title>
<style>
html,body{margin:0;padding:0;background:#0f1216;color:#d7dce3;
 font:13px/1.45 ui-monospace,"DejaVu Sans Mono",Menlo,Consolas,monospace}
#bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;padding:8px 12px;
 border-bottom:1px solid #262c34;background:#12161b}
#bar h1{font-size:13px;margin:0 10px 0 0;color:#8fd0ff;font-weight:700;letter-spacing:.5px}
button{background:#1a2027;color:#d7dce3;border:1px solid #333c47;padding:4px 14px;font:inherit;cursor:pointer}
button.on{background:#1f4e79;border-color:#2f6ea3;color:#fff}
label{color:#8a94a3}
select,input{background:#1a2027;color:#d7dce3;border:1px solid #333c47;padding:3px 6px;font:inherit}
input[type=number]{width:90px}
input[type=text]{width:170px}
#count{margin-left:auto;color:#8a94a3}
#hold{width:100%;overflow:auto}
table{border-collapse:collapse;width:100%}
th,td{padding:3px 9px;border-right:1px solid #1b2128;border-bottom:1px solid #1b2128;
 text-align:right;white-space:nowrap}
thead th{position:sticky;top:0;background:#181e25;color:#9fc3e8;cursor:pointer;
 user-select:none;border-bottom:2px solid #333c47;z-index:4}
thead th:hover{background:#1f2730}
th:first-child,td:first-child{position:sticky;left:0;text-align:left;background:#12161b;z-index:3}
thead th:first-child{background:#181e25;z-index:6}
tbody tr:hover td{background:#1b242e}
td.null{color:#454e5a}
footer{padding:8px 12px;color:#727d8c;border-top:1px solid #262c34;font-size:12px}
</style>
</head>
<body>
<div id="bar">
<h1>BBPRO '98 WIDE STATS</h1>
<button id="bbat" class="on">Batting</button>
<button id="bpit">Pitching</button>
<label>scope
<select id="scope">
<option value="0">Current</option>
<option value="1" selected>Last season</option>
<option value="2">Career</option>
</select></label>
<label><span id="minlbl">min AB</span> <input id="min" type="number" min="0" value="100"></label>
<label>filter <input id="filt" type="text" placeholder="name..."></label>
<span id="count">loading...</span>
</div>
<div id="hold">
<table>
<thead id="th"></thead>
<tbody id="tb"></tbody>
</table>
</div>
<footer>oWAR~ and pWAR~ are approximations: offense-only / pitching-only, no defense or
position adjustment. OBP excludes HBP and SF. Click a header to sort, click again to
reverse; empty cells are nulls and always sort last.</footer>
<script>
'use strict';
var kind='bat',scope=1,minv=100,filt='',rows=[],cols=[],num=[],si=-1,sd=1;
function $(i){return document.getElementById(i);}
function load(){
  fetch('/api?kind='+kind+'&scope='+scope+'&min='+minv,{cache:'no-store'})
  .then(function(r){return r.json().then(function(j){return {ok:r.ok,status:r.status,j:j};});})
  .then(function(o){
    if(!o.ok){$('count').textContent='error: '+(o.j.error||('http '+o.status));return;}
    var j=o.j;
    if(j.scopes_available&&j.scopes_available.length){
      var av=j.scopes_available,opts=$('scope').options;
      for(var k=0;k<opts.length;k++)opts[k].disabled=av.indexOf(+opts[k].value)<0;
      if(av.indexOf(scope)<0){scope=av[0];$('scope').value=String(scope);return load();}
    }
    cols=j.columns;rows=j.rows;si=-1;sd=1;
    $('minlbl').textContent=kind==='bat'?'min AB':'min OUTS';
    render();
  })
  .catch(function(e){$('count').textContent='error: '+e;});
}
function render(){
  num=cols.map(function(c,i){
    for(var k=0;k<rows.length;k++){var v=rows[k][i];
      if(v!==null&&v!==undefined)return typeof v==='number';}
    return false;});
  var thead=$('th');thead.textContent='';
  var hr=document.createElement('tr');
  cols.forEach(function(c,i){
    var th=document.createElement('th');
    th.textContent=c+(i===si?(sd>0?' ▲':' ▼'):'');
    th.onclick=function(){if(si===i)sd=-sd;else{si=i;sd=num[i]?-1:1;}render();};
    hr.appendChild(th);
  });
  thead.appendChild(hr);
  var f=filt.toLowerCase();
  var view=rows.filter(function(r){
    return !f||String(r[0]).toLowerCase().indexOf(f)>=0;});
  if(si>=0){
    view.sort(function(x,y){
      var a=x[si],b=y[si];
      if(a===null||a===undefined||b===null||b===undefined){
        var an=(a===null||a===undefined),bn=(b===null||b===undefined);
        return an&&bn?0:(an?1:-1);
      }
      var c=(typeof a==='number'&&typeof b==='number')?a-b:String(a).localeCompare(String(b));
      return sd*c;
    });
  }
  var tb=$('tb');tb.textContent='';
  view.forEach(function(r){
    var tr=document.createElement('tr');
    r.forEach(function(v){
      var td=document.createElement('td');
      if(v===null||v===undefined){td.textContent='';td.className='null';}
      else td.textContent=String(v);
      tr.appendChild(td);
    });
    tb.appendChild(tr);
  });
  $('count').textContent=view.length+' of '+rows.length+' players';
}
$('bbat').onclick=function(){kind='bat';minv=100;$('min').value='100';$('bbat').classList.add('on');$('bpit').classList.remove('on');load();};
$('bpit').onclick=function(){kind='pit';minv=90;$('min').value='90';$('bpit').classList.add('on');$('bbat').classList.remove('on');load();};
$('scope').onchange=function(e){scope=+e.target.value;load();};
$('min').onchange=function(e){var v=parseInt(e.target.value,10);minv=(isNaN(v)||v<0)?0:v;load();};
$('filt').oninput=function(e){filt=e.target.value;render();};
load();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = 'bbwide/1.0'

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, code, obj):
        self._send(code, json.dumps(obj).encode('utf-8'), 'application/json; charset=utf-8')

    def do_GET(self):
        try:
            self._route()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _route(self):
        u = urlparse(self.path)
        if u.path == '/':
            self._send(200, PAGE.encode('utf-8'), 'text/html; charset=utf-8')
            return
        if u.path == '/favicon.ico':
            self._send(204, b'', 'image/x-icon')
            return
        if u.path != '/api':
            self.send_json(404, {'error': 'not found'})
            return
        q = parse_qs(u.query)
        kind = q.get('kind', ['bat'])[0]
        try:
            scope = int(q.get('scope', ['1'])[0])
            minv = int(q.get('min', ['0'])[0])
        except ValueError:
            self.send_json(400, {'error': 'bad scope/min'})
            return
        if kind not in ('bat', 'pit'):
            self.send_json(400, {'error': 'bad kind (bat|pit)'})
            return
        if scope not in (0, 1, 2):
            self.send_json(400, {'error': 'bad scope (0|1|2)'})
            return
        if minv < 0:
            self.send_json(400, {'error': 'bad min (>=0)'})
            return
        try:
            if kind == 'bat':
                cols, rows = BAT_COLS, bat_table(SNAP, scope, minv)
            else:
                cols, rows = PIT_COLS, pit_table(SNAP, scope, minv)
            avail = scopes_available(SNAP)
        except Exception as e:
            self.send_json(500, {'error': str(e)})
            return
        self.send_json(200, {'columns': cols, 'rows': rows,
                             'scopes_available': avail, 'snap': SNAP})

    def do_POST(self):
        self.send_json(405, {'error': 'GET only'})
    do_PUT = do_POST
    do_DELETE = do_POST


def dump_tsv(kind, scope, minv, snap):
    if kind == 'bat':
        cols, rows = BAT_COLS, bat_table(snap, scope, minv)
    else:
        cols, rows = PIT_COLS, pit_table(snap, scope, minv)
    sys.stdout.write('\t'.join(cols) + '\n')
    for r in rows:
        sys.stdout.write('\t'.join('' if v is None else str(v) for v in r) + '\n')


def main(argv):
    global SNAP
    snap = DEFAULT_SNAP
    port = 8099
    dump = None
    try:
        i = 1
        while i < len(argv):
            a = argv[i]
            if a == '--snap':
                snap = argv[i + 1]; i += 2
            elif a == '--port':
                port = int(argv[i + 1]); i += 2
            elif a == '--dump':
                kind = argv[i + 1]
                scope = int(argv[i + 2])
                i += 3
                minv = 0
                if i < len(argv) and not argv[i].startswith('--'):
                    minv = int(argv[i]); i += 1
                dump = (kind, scope, minv)
            elif a in ('-h', '--help'):
                sys.stdout.write(USAGE)
                return 0
            else:
                sys.stderr.write('bad arg: %s\n' % a)
                return 2
    except (IndexError, ValueError):
        sys.stderr.write(USAGE)
        return 2
    SNAP = snap
    if dump:
        kind, scope, minv = dump
        if kind not in ('bat', 'pit') or scope not in (0, 1, 2) or minv < 0:
            sys.stderr.write(USAGE)
            return 2
        try:
            dump_tsv(kind, scope, minv, snap)
        except Exception as e:
            sys.stderr.write('error: %s\n' % e)
            return 1
        return 0
    srv = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    sys.stderr.write('bbwide: http://127.0.0.1:%d/  snap=%s\n' % (port, snap))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))

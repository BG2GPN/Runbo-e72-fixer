# -*- coding: utf-8 -*-
"""
对讲机一键修复工具 —— 本地服务端
连接 Android 对讲机后，一键完成：
  1. 停用 runbo 管控服务（修复拨号秒挂）
  2. 停用定制默认设置组件（壁纸不再被开机还原）
  3. 重新启用浏览器 / 短信 / 快速搜索
  4. 开启 VoLTE
  5. 恢复「第三方 APK 安装授权」（免密码自由安装）
  6. 自动重启
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

VERSION = "1.0"
CREATE_NO_WINDOW = 0x08000000

ROOT = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
TOOL_DIR = os.path.join(ROOT, "RadioFixTool")
ASSETS = ["adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll", "libwinpthread-1.dll", "placeholder.apk"]


def resource(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(base, name)
    return p if os.path.exists(p) else None


def prepare():
    os.makedirs(TOOL_DIR, exist_ok=True)
    for name in ASSETS:
        src = resource(name)
        if not src:
            continue
        dst = os.path.join(TOOL_DIR, name)
        try:
            if os.path.exists(dst) and os.path.getsize(dst) == os.path.getsize(src):
                continue
            shutil.copy2(src, dst)
        except Exception:
            pass


# ---------------------------------------------------------------- adb 封装

def adb(args, timeout=60):
    exe = os.path.join(TOOL_DIR, "adb.exe")
    env = os.environ.copy()
    env["PATH"] = TOOL_DIR + os.pathsep + env.get("PATH", "")
    try:
        p = subprocess.run([exe] + args, capture_output=True, timeout=timeout,
                           creationflags=CREATE_NO_WINDOW, cwd=TOOL_DIR, env=env)
    except subprocess.TimeoutExpired:
        return -9, "命令超时"
    except Exception as e:
        return -1, str(e)
    raw = (p.stdout or b"") + (p.stderr or b"")
    for enc in ("utf-8", "gbk"):
        try:
            return p.returncode, raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return p.returncode, raw.decode("utf-8", "replace")


def sh(serial, cmd, timeout=40):
    if serial:
        return adb(["-s", serial, "shell", cmd], timeout)
    return adb(["shell", cmd], timeout)


def list_devices():
    rc, out = adb(["devices", "-l"], 25)
    res = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices") or line.startswith("*"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        model = ""
        for p in parts:
            if p.startswith("model:"):
                model = p[6:].replace("_", " ")
        res.append({"serial": parts[0], "state": parts[1], "model": model or "未知机型", "android": ""})
    for d in res:
        if d["state"] == "device":
            d["android"] = sh(d["serial"], "getprop ro.build.version.release", 15)[1].strip()
    return res


def pkgs(serial, args=""):
    rc, out = sh(serial, "pm list packages " + args, 40)
    s = set()
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("package:"):
            s.add(line[8:])
    return s


def pkg_exists(serial, p):
    return p in pkgs(serial, p)


def pkg_disabled(serial, p):
    return p in pkgs(serial, "-d")


def get_status(serial):
    allp = pkgs(serial)
    dis = pkgs(serial, "-d")
    st = sh(serial, "getprop sys.appinstall.state", 15)[1].strip()
    return {
        "call": ("com.runbo.sdk_service" not in allp) or ("com.runbo.sdk_service" in dis),
        "wall": ("com.tintele.DoDefaultSetting" not in allp) or ("com.tintele.DoDefaultSetting" in dis),
        "apps": ("com.android.browser" in allp and "com.android.browser" not in dis),
        "install": st == "1",
        "state": st,
        "volte": sh(serial, "getprop persist.sys.volte.enable", 15)[1].strip(),
    }


# ---------------------------------------------------------------- 任务

class Job(object):
    def __init__(self, jid):
        self.id = jid
        self.logs = []
        self.running = True
        self.done = False
        self.cur = 0
        self.total = 0
        self.summary = ""
        self.lock = threading.Lock()

    def add(self, text, kind=0):
        with self.lock:
            self.logs.append([kind, text])

    def snapshot(self, start):
        with self.lock:
            return {"id": self.id, "logs": self.logs[start:], "n": len(self.logs),
                    "running": self.running, "done": self.done,
                    "cur": self.cur, "total": self.total, "summary": self.summary}


JOB = None
NEXT_ID = 0
JOB_LOCK = threading.Lock()


def step_call(job, serial):
    pkg = "com.runbo.sdk_service"
    if not pkg_exists(serial, pkg):
        job.add("本机未安装该管控服务，跳过", 2)
        return "skip"
    if pkg_disabled(serial, pkg):
        job.add("已处于停用状态", 1)
        return "ok"
    job.add("停用 " + pkg)
    sh(serial, "pm disable-user --user 0 " + pkg)
    time.sleep(0.8)
    if pkg_disabled(serial, pkg):
        job.add("完成 · 通话不会再被强制挂断", 1)
        return "ok"
    job.add("失败 · 请确认设备已允许 USB 调试", 3)
    return "fail"


def step_wall(job, serial):
    pkg = "com.tintele.DoDefaultSetting"
    if not pkg_exists(serial, pkg):
        job.add("本机没有该定制组件，跳过", 2)
        return "skip"
    if pkg_disabled(serial, pkg):
        job.add("已处于停用状态", 1)
        return "ok"
    job.add("停用 " + pkg + "（它会开机强改壁纸并禁用浏览器）")
    sh(serial, "pm disable-user --user 0 " + pkg)
    time.sleep(0.8)
    if pkg_disabled(serial, pkg):
        job.add("完成 · 壁纸不会再被还原", 1)
        return "ok"
    job.add("失败", 3)
    return "fail"


def step_apps(job, serial):
    apps = ["com.android.browser", "com.android.messaging", "com.android.quicksearchbox"]
    allp = pkgs(serial)
    hit = [a for a in apps if a in allp]
    if not hit:
        job.add("本机没有需要恢复的系统应用，跳过", 2)
        return "skip"
    for a in hit:
        sh(serial, "pm enable " + a)
    time.sleep(0.6)
    dis = pkgs(serial, "-d")
    bad = [a for a in hit if a in dis]
    job.add("已启用：" + "、".join(hit))
    if bad:
        job.add("仍被禁用：" + "、".join(bad), 3)
        return "fail"
    job.add("完成", 1)
    return "ok"


def step_volte(job, serial):
    sh(serial, "setprop persist.sys.volte.enable true")
    time.sleep(0.3)
    v = sh(serial, "getprop persist.sys.volte.enable", 15)[1].strip()
    if v.lower() == "true":
        job.add("VoLTE 已开启（重启后保持）", 1)
        return "ok"
    job.add("设置未生效，当前值：" + (v or "空"), 2)
    return "skip"


def step_install(job, serial):
    job.add("先把安装授权置为开启")
    sh(serial, "setprop sys.appinstall.state 1")
    sh(serial, "settings put system app_install_authorize 1")
    time.sleep(0.3)

    if pkg_exists(serial, "runbo.android.poc"):
        job.add("授权引导组件已存在，无需安装", 1)
    else:
        job.add("安装授权引导组件（用于修复开机恢复链路）")
        rc, out = adb(["-s", serial, "install", "-r",
                       os.path.join(TOOL_DIR, "placeholder.apk")], 120)
        if "Success" in out:
            job.add("安装成功", 1)
        else:
            tail = [x for x in out.strip().splitlines() if x.strip()]
            job.add("安装失败：" + (tail[-1] if tail else "未知原因"), 3)
            return "fail"

    st = sh(serial, "getprop sys.appinstall.state", 15)[1].strip()
    if st == "1":
        job.add("授权属性已生效，现在可以直接安装软件", 1)
        return "ok"
    job.add("授权属性未生效（当前：" + (st or "空") + "），开机后会自动恢复", 2)
    return "skip"


def step_reboot(job, serial):
    job.add("正在重启设备，约 1 分钟后重新上线")
    adb(["-s", serial, "reboot"], 20)
    time.sleep(1)
    return "ok"


def run_fix(job, serial, opts):
    try:
        steps = []
        if opts.get("call"):
            steps.append(("修复拨号秒挂", step_call))
        if opts.get("wall"):
            steps.append(("锁定壁纸", step_wall))
        if opts.get("apps"):
            steps.append(("恢复浏览器与短信", step_apps))
        if opts.get("volte"):
            steps.append(("开启 VoLTE", step_volte))
        if opts.get("install"):
            steps.append(("恢复安装授权", step_install))
        if opts.get("reboot"):
            steps.append(("重启设备", step_reboot))

        job.total = len(steps)
        ok = skip = fail = 0
        for i, (name, fn) in enumerate(steps, 1):
            job.cur = i - 1
            job.add("\n[%d/%d] %s" % (i, len(steps), name), 4)
            try:
                r = fn(job, serial)
            except Exception as e:
                job.add("异常：" + str(e), 3)
                r = "fail"
            if r == "ok":
                ok += 1
            elif r == "skip":
                skip += 1
            else:
                fail += 1
            job.cur = i
            time.sleep(0.15)
        job.summary = "完成：成功 %d 项 · 跳过 %d 项 · 失败 %d 项" % (ok, skip, fail)
        job.add("\n" + job.summary, 1 if fail == 0 else 2)
    except Exception as e:
        job.add("执行中断：" + str(e), 3)
        job.summary = "执行中断：" + str(e)
    finally:
        job.running = False
        job.done = True


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, data, ctype):
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(data)
        except Exception:
            pass

    def _json(self, obj):
        self._send(json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        path = u.path

        if path in ("/", "/index.html"):
            p = resource("ui.html")
            if not p:
                self._send("<h1>ui.html 缺失</h1>", "text/html; charset=utf-8")
                return
            with open(p, encoding="utf-8") as f:
                self._send(f.read(), "text/html; charset=utf-8")
            return

        if path == "/api/ping":
            self._json({"ok": True, "version": VERSION})
            return

        if path == "/api/devices":
            try:
                self._json({"devices": list_devices(), "adb": os.path.join(TOOL_DIR, "adb.exe")})
            except Exception as e:
                self._json({"devices": [], "error": str(e)})
            return

        if path == "/api/status":
            serial = (q.get("serial") or [""])[0]
            if not serial:
                self._json({"ok": False, "error": "缺少设备"})
                return
            try:
                self._json({"ok": True, "status": get_status(serial)})
            except Exception as e:
                self._json({"ok": False, "error": str(e)})
            return

        if path == "/api/log":
            jid = int((q.get("id") or ["0"])[0] or 0)
            start = int((q.get("from") or ["0"])[0] or 0)
            with JOB_LOCK:
                job = JOB
            if not job or job.id != jid:
                self._json({"id": jid, "logs": [], "n": 0, "running": False, "done": True,
                            "cur": 0, "total": 0, "summary": "任务不存在"})
                return
            self._json(job.snapshot(start))
            return

        if path == "/api/quit":
            self._json({"ok": True})
            threading.Timer(0.4, lambda: os._exit(0)).start()
            return

        self._send("not found", "text/plain; charset=utf-8")

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n).decode("utf-8") if n else "{}"
        try:
            data = json.loads(body or "{}")
        except Exception:
            data = {}

        if u.path == "/api/fix":
            serial = data.get("serial") or ""
            opts = data.get("opts") or {}
            if not serial:
                self._json({"ok": False, "error": "未选择设备"})
                return
            global JOB, NEXT_ID
            with JOB_LOCK:
                if JOB and not JOB.done:
                    self._json({"ok": False, "error": "已有任务在执行"})
                    return
                NEXT_ID += 1
                JOB = Job(NEXT_ID)
                job = JOB
            threading.Thread(target=run_fix, args=(job, serial, opts), daemon=True).start()
            self._json({"ok": True, "id": job.id})
            return

        self._json({"ok": False, "error": "unknown"})


def already_running(port):
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:%d/api/ping" % port, timeout=1.2) as r:
            return b'"ok": true' in r.read()
    except Exception:
        return False


def open_window(url):
    cands = [
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                     r"Microsoft\Edge\Application\msedge.exe"),
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                     r"Microsoft\Edge\Application\msedge.exe"),
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                     r"Google\Chrome\Application\chrome.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                     r"Google\Chrome\Application\chrome.exe"),
    ]
    for c in cands:
        if os.path.exists(c):
            try:
                subprocess.Popen([c, "--app=" + url, "--window-size=1000,820",
                                  "--no-first-run", "--disable-features=Translate"],
                                 creationflags=CREATE_NO_WINDOW)
                return
            except Exception:
                pass
    webbrowser.open(url)


def main():
    prepare()

    # 已有实例就直接把窗口拉起来，避免重复进程
    port_file = os.path.join(TOOL_DIR, "port.txt")
    if os.path.exists(port_file):
        try:
            old = int(open(port_file).read().strip())
            if already_running(old):
                open_window("http://127.0.0.1:%d/" % old)
                return
        except Exception:
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = srv.server_address[1]
    try:
        with open(port_file, "w") as f:
            f.write(str(port))
    except Exception:
        pass

    threading.Thread(target=srv.serve_forever, daemon=True).start()
    if os.environ.get("RADIOFIX_NOOPEN") != "1":
        open_window("http://127.0.0.1:%d/" % port)

    # 主线程常驻
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()

import json
import io
import base64
import subprocess
import threading
import time
from collections import deque
from datetime import datetime

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from flask import Flask, render_template, send_from_directory, jsonify, request


# --- Загрузка конфигурации ---
def load_config():
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "server_location": "UMKA Cluster",
            "software_version": "1.0.0",
            "retention_hours": 72,
            "targets": [],
            "ssh_interval": 5,
            "ajax_interval": 15
        }


config = load_config()

SOFTWARE_VERSION = config.get('software_version', '1.0.0')  # Получаем версию ПО
RETENTION_HOURS = config.get('retention_hours', 72)
SSH_INTERVAL = config.get("ssh_interval", 5)
AJAX_INTERVAL = config.get("ajax_interval", 15)
targets = config.get('targets', [])

# количество точек в памяти на один хост
MAX_POINTS = int(RETENTION_HOURS * 3600 / SSH_INTERVAL)

# Глобальные данные в ОЗУ
data_store = {t['name']: deque(maxlen=MAX_POINTS) for t in targets}
current_stats = {t['name']: {"online": 0, "cpu": 0, "mem": 0, "temp": 0} for t in targets}

# --- КЭШ ДЛЯ ГРАФИКОВ ---
plot_cache = {
    1:   {"img": None, "time": 0},
    8:   {"img": None, "time": 0},
    24:  {"img": None, "time": 0},
    72:  {"img": None, "time": 0},
    168: {"img": None, "time": 0},
}


# --- SSH через subprocess ---
def ssh_cmd(host, port, username, command):
    cmd = [
        "ssh",
        "-oHostKeyAlgorithms=+ssh-rsa",
        "-oPubkeyAcceptedAlgorithms=+ssh-rsa",
        "-oStrictHostKeyChecking=no",
        "-p", str(port),
        f"{username}@{host}",
        command
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=2  # Ожидание 2 секунды
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()
    except Exception:
        return None


def get_metrics(host, port, user):
    """Сбор CPU, памяти и температуры через SSH"""
    out = ssh_cmd(
        host, port, user,
        "cat /proc/loadavg; "
        "grep -E 'MemTotal|MemFree' /proc/meminfo; "
        "cat /sys/class/thermal/thermal_zone0/temp"
    )

    if not out:
        return None

    lines = out.split("\n")
    if len(lines) < 4:
        return None

    try:
        cpu = float(lines[0].split()[0])
        total = int(lines[1].split()[1])
        free = int(lines[2].split()[1])
        used_mb = round((total - free) / 1024, 1)

        temp_raw = int(lines[3])
        temp_c = round(temp_raw / 1000, 2)

        return cpu, used_mb, temp_c
    except Exception:
        return None


# --- Поток опроса устройств ---
def ssh_worker(target):
    name = target['name']
    host = target['host']
    user = target['user']
    port = target.get('port', 22)

    while True:
        st, cpu, mem, temp = 0, 0.0, 0.0, 0.0

        # Попытка №1
        res = get_metrics(host, port, user)
        
        # Если первая попытка провалилась, делаем быструю повторную
        if not res:
            time.sleep(0.5)
            res = get_metrics(host, port, user)

        if res:
            cpu, mem, temp = res
            st = 1

        data_store[name].append((datetime.now(), st, cpu, mem, temp))
        current_stats[name] = {"online": st, "cpu": cpu, "mem": mem, "temp": temp}

        time.sleep(SSH_INTERVAL)


for target in targets:
    threading.Thread(target=ssh_worker, args=(target,), daemon=True).start()


app = Flask(__name__)


def generate_plot(hours):
    """Генерация графиков за указанный диапазон (hours)"""
    cutoff = datetime.now().timestamp() - hours * 3600

    plt.style.use('dark_background')
    fig, (ax1, ax2, ax3, ax4) = plt.subplots(4, 1, figsize=(12, 14), sharex=False)

    xfmt = mdates.DateFormatter('%H:%M:%S')

    global_max_cpu = 0.0
    global_max_mem = 0.0

    for i, (name, data) in enumerate(data_store.items()):
        if not data:
            continue

        filtered = [d for d in data if d[0].timestamp() >= cutoff]
        if not filtered:
            continue

        total_pts = len(filtered)
        step = max(1, total_pts // 1000)

        t_red, s_red, c_red, m_red, temp_red = [], [], [], [], []

        for j in range(0, total_pts, step):
            chunk = filtered[j:j + step]
            t_red.append(chunk[0][0])
            s_red.append(min(item[1] for item in chunk))
            c_red.append(max(item[2] for item in chunk))
            m_red.append(max(item[3] for item in chunk))
            temp_red.append(max(item[4] for item in chunk))

        if c_red:
            local_max_cpu = max(c_red)
            if local_max_cpu > global_max_cpu:
                global_max_cpu = local_max_cpu

        if m_red:
            local_max_mem = max(m_red)
            if local_max_mem > global_max_mem:
                global_max_mem = local_max_mem

        ax1.step(t_red, [v + (i * 0.02) for v in s_red], label=name, where='post', linewidth=1.5)
        ax2.plot(t_red, c_red, label=name, alpha=0.8)
        ax3.plot(t_red, m_red, label=name, alpha=0.8)
        ax4.plot(t_red, temp_red, label=name, alpha=0.8)

    if global_max_cpu > 0:
        cpu_upper_limit = max(0.5, global_max_cpu * 1.15)
    else:
        cpu_upper_limit = 0.5

    if global_max_mem > 0:
        mem_upper_limit = global_max_mem * 1.15
    else:
        mem_upper_limit = 200.0

    axes = [ax1, ax2, ax3, ax4]
    titles = ["Связь (ON/OFF)", "Загрузка CPU", "Память (МБ)", "Температура (°C)"]
    ylabels = ["Status", "Load Avg", "Memory MB", "°C"]
    
    limits = [(-0.2, 1.2), (0, cpu_upper_limit), (0, mem_upper_limit), (20, 100)]

    for i, ax in enumerate(axes):
        ax.set_title(titles[i], color='orange', pad=12)
        ax.set_ylabel(ylabels[i], color='orange')
        ax.set_ylim(limits[i])
        ax.xaxis.set_major_formatter(xfmt)
        ax.tick_params(axis='x', labelbottom=True, rotation=15, labelsize=9)
        ax.grid(True, linestyle='--', alpha=0.15)

        handles, labels = ax.get_legend_handles_labels()
        if labels:
            ax.legend(loc='upper left', ncol=4, fontsize=8, frameon=False)

    ax1.set_yticks([0, 1])
    ax1.set_yticklabels(["OFF", "ON"])

    plt.tight_layout(pad=3.5)

    img = io.BytesIO()
    plt.savefig(img, format='png', transparent=True, dpi=100)
    plt.close(fig)
    return base64.b64encode(img.getvalue()).decode('utf8')


@app.route('/')
def index():
    # Передаем версию ПО в шаблон при рендере
    return render_template("index.html", ajax_interval=AJAX_INTERVAL, software_version=SOFTWARE_VERSION)


@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico', mimetype='image/vnd.microsoft.icon')


@app.route('/api/stats')
def api_stats():
    return jsonify(current_stats)


@app.route('/api/plot')
def api_plot():
    hours = int(request.args.get("hours", 1))
    force = request.args.get("force", "0") == "1"
    now = time.time()

    if hours not in plot_cache:
        plot_cache[hours] = {"img": None, "time": 0}

    if not force and plot_cache[hours]["img"] is not None and now - plot_cache[hours]["time"] < AJAX_INTERVAL:
        return jsonify({"img": plot_cache[hours]["img"]})

    img = generate_plot(hours)
    plot_cache[hours]["img"] = img
    plot_cache[hours]["time"] = now

    return jsonify({"img": img})


@app.route('/api/reset', methods=['POST'])
def api_reset():
    global data_store, current_stats, plot_cache
    
    for target in targets:
        name = target['name']
        data_store[name].clear()
        current_stats[name] = {"online": 0, "cpu": 0, "mem": 0, "temp": 0}
        
    for hours in plot_cache:
        plot_cache[hours] = {"img": None, "time": 0}
        
    return jsonify({"status": "success", "message": "Данные успешно сброшены"})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=1200, debug=False)

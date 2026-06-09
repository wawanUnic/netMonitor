// читаем интервал из HTML
const ajaxInterval = parseInt(document.getElementById("config").dataset.interval) * 1000;

// текущий выбранный диапазон (1 час по умолчанию)
let currentHours = 1;

// ---------------------------
// Обновление статусов (AJAX)
// ---------------------------
function updateStats() {
    fetch('/api/stats')
        .then(r => r.json())
        .then(data => {
            let html = "";
            let keys = Object.keys(data);
            document.getElementById("count").innerText = keys.length;

            keys.forEach(name => {
                let st = data[name];
                let color = st.online ? "#28a745" : "#dc3545";

                html += `
                <div class="node-card">
                    <div class="status-indicator" style="background-color: ${color};"></div>
                    <div style="font-weight: bold; margin-bottom: 5px;">${name}</div>
                    <div class="stats-line">
                        CPU: <b>${st.cpu}</b> |
                        Mem: <b>${st.mem}MB</b> |
                        Temp: <b>${st.temp}°C</b>
                    </div>
                </div>`;
            });

            document.getElementById("stats-grid").innerHTML = html;
        });
}

// ---------------------------
// Обновление графика (AJAX)
// параметр force=true заставляет сервер проигнорировать кэш времени
// ---------------------------
function updatePlot(force = false) {
    const url = `/api/plot?hours=${currentHours}${force ? '&force=1' : ''}`;
    fetch(url)
        .then(r => r.json())
        .then(data => {
            if (data.img) {
                document.getElementById("plot").src = "data:image/png;base64," + data.img;
            }
        });
}

// ---------------------------
// Обновление всего сразу (для интервала используется обычный запрос с кэшем)
// ---------------------------
function updateAll() {
    updateStats();
    updatePlot(false); 
}

// ---------------------------
// Инициализация событий при загрузке страницы
// ---------------------------
document.addEventListener("DOMContentLoaded", () => {
    
    // Обработка кнопок переключения диапазонов часов
    document.querySelectorAll(".range-btn").forEach(btn => {
        btn.addEventListener("click", function () {
            // Снимаем выделение со всех кнопок
            document.querySelectorAll(".range-btn").forEach(b => b.classList.remove("active"));

            // Выделяем текущую
            this.classList.add("active");

            // Читаем диапазон
            currentHours = parseInt(this.dataset.hours);

            // МГНОВЕННО обновляем график в обход серверного кэша
            updatePlot(true);
        });
    });

    // Обработка кнопки Сброс данных
    const resetButton = document.getElementById("reset-data-btn");
    if (resetButton) {
        resetButton.addEventListener("click", function() {
            if (confirm("Вы уверены, что хотите полностью сбросить все накопленные метрики и графики?")) {
                fetch('/api/reset', { method: 'POST' })
                    .then(r => r.json())
                    .then(data => {
                        if (data.status === "success") {
                            // Очищаем картинку на экране, пока генерируется пустой график
                            document.getElementById("plot").src = ""; 
                            // Запрашиваем обновление статусов и графика без задержек
                            updateStats();
                            updatePlot(true);
                        }
                    })
                    .catch(err => console.error("Ошибка сброса:", err));
            }
        });
    }
});

// Первичная мгновенная загрузка (при открытии страницы генерируем график сразу)
updateStats();
updatePlot(true);

// Фоновый интервал обновления (использует кэш, чтобы по таймеру не нагружать CPU)
setInterval(updateAll, ajaxInterval);

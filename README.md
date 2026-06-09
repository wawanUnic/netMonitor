# netMonitor
Сервис для долговременного мониторинга приборов УМКА

## Настройка выполнена для устройства RaspberryPi.  
- Плата: Raspberry Pi 2 Model B
- ОСистема: Raspberry Pi OS Lite (Debian)
- Архитектура: ARMv7
- ЦПУ: Broadcom BCM2836, 4 ядра ARM Cortex‑A7 @ 900 МГц
- ОЗУ: 1 ГБ LPDDR2
- Сеть: 100 Мбит/с Ethernet

## Открытые порты.
- 22 -- основной порт для администрирования
- 1200 -- веб-интерфейс сервиса 

## Создаем папку для проекта и виртуальное окружение.
```
mkdir netMonitor
cd netMonitor
python -m venv venv
source venv/bin/activate
(deactivate -- для выхода из виртуального окружения)
```

## Устанавливаем библиотеки внутри виртуального окружения.
```
pip install ...
```

Версии бибилотек:
```
...
```

## Добавляем сервис в systemD.

Работаем от пользователя pi, поэтому права на папку пользователя менять не нужно (drwx------). Создаем файл /etc/systemd/system/netMonitor.service

(Для простого ручного испытания достаточно - python app.py)

```
[Unit]
Description=netMonitor
After=network-online.target nss-user-lookup.target

[Service]
User=pi
Group=pi
WorkingDirectory=/home/pi/netMonitor
Environment="PYTHONPATH=/home/pi/netMonitor/venv/lib/python3.13/site-packages" --- python3.13?
ExecStartPre=/usr/bin/sleep 10
ExecStart=/home/pi/netMonitor/venv/bin/python3.13 /home/pi/netMonitor/app.py --- python3.13?

RestartSec=10
Restart=always
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

## Настраиваем systemD.
```
sudo systemctl daemon-reload
sudo systemctl enable --now netMonitor.service
systemctl status netMonitor.service
```

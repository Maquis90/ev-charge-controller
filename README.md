# EV Charge Controller

evcc-ähnlicher Lade-Controller für einen Tesla (BLE über ESPHome) mit „dummer“ Wallbox. Daten und Steuerung laufen über die Home-Assistant-API.

## Modi
- **Express**: feste Ampere (`express_amps`).
- **Intelligent**: folgt dem Überschuss (PV + optional Hausbatterie), zwischen `min_amps` und `max_amps`; Netzbezug minimal (`grid_offset_w`). Mit `pause_below_min` wird unter Min-Strom pausiert statt Netz zu beziehen.
- **Ziele**: `max_soc` stoppt die Ladung; `min_soc_tomorrow` bis `deadline` erzwingt Volllast (`max_amps`) erst, wenn es sonst nicht mehr rechtzeitig erreichbar ist (so wenig Netz wie möglich).

## Start
```
cp config.example.yaml config.yaml   # Entity-IDs + HA-Token anpassen, dry_run zuerst true
pip install -r requirements.txt
python -m evcc_app                   # UI: http://localhost:8088
```
Docker: `docker build -t evcc-app . && docker run -p 8088:8088 -v $PWD:/data evcc-app` (`config.yaml` in `/data`).
Tests: `pip install pytest && pytest`.

Hinweis: Befehle an den Tesla werden mind. alle 20 s gesendet (BLE ist langsam). Änderungen in der UI werden in `settings.json` gespeichert.

## Home-Assistant-App
Repository in HA hinzufügen: Einstellungen → Apps → App-Store → ⋮ → Repositories → URL dieses Repos. Dann „EV Charge Controller" installieren, Konfiguration prüfen (`dry_run`), starten. Das Token wird nicht benötigt (Supervisor-API).

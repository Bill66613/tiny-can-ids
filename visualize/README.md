# Visualize

## How to run

```
cd visualize

pip install -r requirements.txt

export VISUALIZE_DETECTION_BINARY="./can_test_app"

# Chart2 now reads detection results from MQTT
export VISUALIZE_MQTT_HOST="127.0.0.1"
export VISUALIZE_MQTT_PORT="1883"
export VISUALIZE_MQTT_TOPIC="ids/prediction"
# Optional auth
# export VISUALIZE_MQTT_USERNAME="user"
# export VISUALIZE_MQTT_PASSWORD="pass"

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## MQTT message format for Chart2

Chart2 expects JSON payloads in this format:

```json
{
	"attack-type": "dos",
	"model": "tnn",
	"mode": "inference",
	"pred": 0
}
```

Notes:

- `mode` must be `inference`.
- Supported values currently: `attack-type=dos`, `model=tnn|dt`.
- `pred` is normalized to `0|1` before pushing to the chart.
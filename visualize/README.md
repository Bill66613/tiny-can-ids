# Visualize

## How to run

```
cd visualize

pip install -r requirements.txt

export VISUALIZE_DETECTION_BINARY="./can_test_app"

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
import requests
import statistics

app = FastAPI()

# Enable CORS for all origins (safe for a public API like this)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LAT, LON = 40.0456, -86.0086
MODELS = ["ecmwf", "gfs", "icon"]

@app.get("/api/forecast")
def get_weighted_forecast():
    now = datetime.utcnow()
    start_actual = (now - timedelta(days=5)).strftime("%Y-%m-%d")
    end_actual = now.strftime("%Y-%m-%d")

    # Get observed historical data
    actuals_url = f"https://archive-api.open-meteo.com/v1/archive?latitude={LAT}&longitude={LON}&start_date={start_actual}&end_date={end_actual}&hourly=temperature_2m,precipitation,precipitation_probability&timezone=auto"
    actuals = requests.get(actuals_url).json()
    actual_temps = actuals["hourly"]["temperature_2m"]
    actual_probs = actuals["hourly"]["precipitation_probability"]
    actual_amts = actuals["hourly"]["precipitation"]

    model_errors = {model: [] for model in MODELS}

    # Simulate scoring: using current data as forecast vs actuals
    for model in MODELS:
        forecast_url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&hourly=temperature_2m,precipitation,precipitation_probability&models={model}&forecast_days=1&timezone=auto"
        forecast_data = requests.get(forecast_url).json()
        forecast_temps = forecast_data["hourly"]["temperature_2m"][:len(actual_temps)]
        forecast_probs = forecast_data["hourly"]["precipitation_probability"][:len(actual_probs)]
        forecast_amts = forecast_data["hourly"]["precipitation"][:len(actual_amts)]

        temp_error = [abs(f - a) for f, a in zip(forecast_temps, actual_temps)]
        prob_error = [abs(f - a) for f, a in zip(forecast_probs, actual_probs)]
        amt_error = [abs(f - a) for f, a in zip(forecast_amts, actual_amts)]

        model_errors[model] = [
            statistics.mean(temp_error),
            statistics.mean(prob_error),
            statistics.mean(amt_error),
        ]

    # Normalize model scores: lower error = higher weight
    weights = {}
    for i in range(3):  # temp, prob, amt
        total = sum(1 / (model_errors[m][i] + 0.1) for m in MODELS)
        for model in MODELS:
            weights.setdefault(model, [0, 0, 0])
            weights[model][i] = (1 / (model_errors[model][i] + 0.1)) / total

    # Fetch forecasts from each model again for 7 days
    forecast_hours = []
    forecasts_by_model = {}
    for model in MODELS:
        forecast_url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&hourly=temperature_2m,precipitation,precipitation_probability&models={model}&forecast_days=7&timezone=auto"
        fdata = requests.get(forecast_url).json()
        forecasts_by_model[model] = fdata["hourly"]

    hours = forecasts_by_model[MODELS[0]]["time"]
    for i, time in enumerate(hours):
        t_sum = sum(forecasts_by_model[m]["temperature_2m"][i] * weights[m][0] for m in MODELS)
        p_sum = sum(forecasts_by_model[m]["precipitation_probability"][i] * weights[m][1] for m in MODELS)
        a_sum = sum(forecasts_by_model[m]["precipitation"][i] * weights[m][2] for m in MODELS)

        forecast_hours.append({
            "time": time,
            "temperature": round(t_sum, 1),
            "precipitation_probability": round(p_sum),
            "precipitation": round(a_sum, 2)
        })

    return {"hourly": forecast_hours}

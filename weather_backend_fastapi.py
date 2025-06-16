from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
import requests
import statistics
from collections import defaultdict

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
# Using stable, named models only
MODELS = ["icon_se", "meteofrance", "gfs", "ukmet"]

model_hourly_errors_cache = None
summary_cache = None

@app.get("/api/forecast")
def get_weighted_forecast():
    global model_hourly_errors_cache, summary_cache

    try:
        now = datetime.utcnow()
        forecast_hours = []

        # Step 1: Fetch actuals for the past 5 days
        start_actual = (now - timedelta(days=5)).strftime("%Y-%m-%d")
        end_actual = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        actuals_url = f"https://archive-api.open-meteo.com/v1/archive?latitude={LAT}&longitude={LON}&start_date={start_actual}&end_date={end_actual}&hourly=temperature_2m,precipitation,precipitation_probability&timezone=auto"
        actuals_resp = requests.get(actuals_url)
        if not actuals_resp.ok:
            raise HTTPException(status_code=502, detail=f"Failed to fetch actuals: {actuals_resp.status_code}")
        actuals = actuals_resp.json()["hourly"]

        actual_data = list(zip(
            actuals["time"],
            [a * 9/5 + 32 if a is not None else None for a in actuals["temperature_2m"]],
            actuals["precipitation_probability"],
            actuals["precipitation"]
        ))

        # Step 2: Collect all forecasts from each model for each of the past 5 days
        model_hourly_errors = {model: {h: [] for h in range(24)} for model in MODELS}

        for days_ago in range(5, 0, -1):
            day = now - timedelta(days=days_ago)
            forecast_date = day.strftime("%Y-%m-%d")
            for model in MODELS:
                url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&start_date={forecast_date}&end_date={forecast_date}&hourly=temperature_2m,precipitation,precipitation_probability&model={model}&timezone=auto"
                resp = requests.get(url)
                if not resp.ok:
                    continue
                forecast = resp.json()["hourly"]
                for time, ft, fp, fa in zip(
                    forecast["time"],
                    forecast["temperature_2m"],
                    forecast["precipitation_probability"],
                    forecast["precipitation"]
                ):
                    actual_match = next((a for a in actual_data if a[0] == time), None)
                    if actual_match:
                        hour = int(time[11:13])
                        at, ap, aa = actual_match[1:]  # actual temp (F), probability, amount
                        if None not in [ft, fp, fa, at, ap, aa]:
                            ft = ft * 9/5 + 32
                            model_hourly_errors[model][hour].append([
                                abs(ft - at),
                                abs(fp - ap),
                                abs(fa - aa)
                            ])

        # Cache errors for review endpoint
        model_hourly_errors_cache = model_hourly_errors

        # Step 3: Calculate per-hour average error for each model
        weights_by_hour = {}
        best_model_by_hour = {}
        summary_count = defaultdict(lambda: defaultdict(list))
        for hour in range(24):
            weights_by_hour[hour] = {}
            best_model_by_hour[hour] = {"temperature": None, "precipitation_probability": None, "precipitation": None}
            for i, metric in enumerate(["temperature", "precipitation_probability", "precipitation"]):
                errors = {
                    m: statistics.mean([e[i] for e in model_hourly_errors[m][hour]]) if model_hourly_errors[m][hour] else 1e9
                    for m in MODELS
                }
                best_model = min(errors, key=errors.get)
                best_model_by_hour[hour][metric] = best_model
                summary_count[metric][best_model].append(hour)
                total = sum(1 / (errors[m] + 0.1) for m in MODELS)
                for m in MODELS:
                    weights_by_hour[hour].setdefault(m, [0, 0, 0])
                    weights_by_hour[hour][m][i] = (1 / (errors[m] + 0.1)) / total

        # Step 4: Generate plain-language summary
        plain_summary = {}
        for metric, hour_map in summary_count.items():
            lines = []
            for model in MODELS:
                if hour_map[model]:
                    ranges = ', '.join([f"{h:02d}:00" for h in sorted(hour_map[model])])
                    lines.append(f"- {model} was most accurate for {metric} at: {ranges}")
            plain_summary[metric] = '\n'.join(lines)
        summary_cache = plain_summary

        # Step 5: Fetch today + 6-day forecast and apply weighting
        forecasts_by_model = {}
        for model in MODELS:
            url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&hourly=temperature_2m,precipitation,precipitation_probability&model={model}&forecast_days=7&timezone=auto"
            resp = requests.get(url)
            if not resp.ok:
                raise HTTPException(status_code=502, detail=f"Failed to fetch forecast for model {model}: {resp.status_code}")
            forecasts_by_model[model] = resp.json()["hourly"]

        hours = forecasts_by_model[MODELS[0]]["time"]
        for i, time in enumerate(hours):
            hour = int(time[11:13])
            try:
                temp = sum((forecasts_by_model[m]["temperature_2m"][i] or 0) * weights_by_hour[hour][m][0] for m in MODELS)
                temp = temp * 9/5 + 32
                prob = sum((forecasts_by_model[m]["precipitation_probability"][i] or 0) * weights_by_hour[hour][m][1] for m in MODELS)
                amt = sum((forecasts_by_model[m]["precipitation"][i] or 0) * weights_by_hour[hour][m][2] for m in MODELS)
            except Exception:
                continue

            forecast_hours.append({
                "time": time,
                "temperature": round(temp, 1),
                "precipitation_probability": round(prob),
                "precipitation": round(amt, 2)
            })

        return {
            "hourly": forecast_hours,
            "best_model_by_hour": best_model_by_hour,
            "accuracy_summary": plain_summary
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unhandled server error: {str(e)}")

@app.get("/api/review")
def get_model_accuracy_review():
    if not model_hourly_errors_cache or not summary_cache:
        raise HTTPException(status_code=503, detail="No cached model performance data available. Please run /api/forecast first.")

    return {
        "model_hourly_errors": model_hourly_errors_cache,
        "accuracy_summary": summary_cache
    }

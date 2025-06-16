<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Weighted Weather Forecast</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 0; padding: 0; background: #f4f4f4; }
    .container { padding: 20px; max-width: 1000px; margin: auto; background: #fff; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
    h1 { text-align: center; }
    .forecast-day { margin-bottom: 40px; }
    .hour-row { display: flex; font-size: 12px; margin-top: 5px; }
    .hour-cell { flex: 1; padding: 4px; text-align: center; border: 1px solid #ddd; }
    .header { font-weight: bold; background-color: #333; color: white; }
    .explanation { background: #eef; padding: 10px; border-left: 5px solid #88f; margin-top: 20px; }
    .high-temp { background-color: #ff9999 !important; }
    .low-temp { background-color: #b3d9ff !important; }
    .high-rain-chance { background-color: #c0e0ff !important; font-weight: bold; }
    .high-rain-amount { background-color: #99ccff !important; font-weight: bold; }
  </style>
</head>
<body>
  <div class="container">
    <h1>Weighted Weather Forecast</h1>
    <div id="forecast-container"></div>
    <div class="explanation">
      <strong>Forecast Weighting:</strong><br>
      This forecast uses data from multiple weather models provided by Open-Meteo. For each hour of the day, the system checks how accurate each model was over the past 5 days and assigns higher weight to the most reliable sources. This allows each hour's prediction to reflect the best-performing model for that time. Temperature, chance of rain, and precipitation amounts are all calculated using this method.
    </div>
  </div>
  <script>
    async function fetchWeather() {
      const response = await fetch("http://localhost:8000/api/forecast");
      const data = await response.json();
      const forecast = data.hourly;

      const grouped = {};
      forecast.forEach(entry => {
        const date = new Date(entry.time);
        const dayKey = date.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' });
        if (!grouped[dayKey]) grouped[dayKey] = [];
        if (date.getHours() % 2 === 0) grouped[dayKey].push({
          hour: date.getHours(),
          temperature: entry.temperature,
          precipitation_probability: entry.precipitation_probability,
          precipitation: entry.precipitation
        });
      });

      let html = "";
      for (const [day, entries] of Object.entries(grouped)) {
        html += `<div class="forecast-day"><h2>${day}</h2><div class="hour-row header">`;
        entries.forEach(e => html += `<div class="hour-cell">${e.hour}:00</div>`);
        html += `</div>`;

        const temps = entries.map(e => e.temperature);
        const probs = entries.map(e => e.precipitation_probability);
        const amts = entries.map(e => e.precipitation);

        const topTemps = [...entries.keys()].sort((a,b) => temps[b] - temps[a]).slice(0,3);
        const lowTemps = [...entries.keys()].sort((a,b) => temps[a] - temps[b]).slice(0,3);
        const topProbs = [...entries.keys()].sort((a,b) => probs[b] - probs[a]).slice(0,3);
        const topAmts = [...entries.keys()].sort((a,b) => amts[b] - amts[a]).slice(0,3);

        html += `<div class="hour-row">`;
        entries.forEach((e, i) => {
          const cls = topTemps.includes(i) ? 'high-temp' : lowTemps.includes(i) ? 'low-temp' : '';
          html += `<div class="hour-cell ${cls}">${e.temperature}°</div>`;
        });
        html += `</div>`;

        html += `<div class="hour-row">`;
        entries.forEach((e, i) => {
          const cls = topProbs.includes(i) ? 'high-rain-chance' : '';
          html += `<div class="hour-cell ${cls}">${e.precipitation_probability}%</div>`;
        });
        html += `</div>`;

        html += `<div class="hour-row">`;
        entries.forEach((e, i) => {
          const cls = topAmts.includes(i) ? 'high-rain-amount' : '';
          html += `<div class="hour-cell ${cls}">${e.precipitation.toFixed(2)}"</div>`;
        });
        html += `</div></div>`;
      }

      document.getElementById("forecast-container").innerHTML = html;
    }
    fetchWeather();
  </script>
</body>
</html>

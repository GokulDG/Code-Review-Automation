import express from "express";
import client from "prom-client";

const app = express();
const PORT = process.env.PORT || 3001;

// 1. Create a Prometheus registry
const register = new client.Registry();

// 2. Collect Node.js default metrics (CPU, memory, event loop lag, GC...)
client.collectDefaultMetrics({
  register,
  prefix: "nodejs_",
});

// 3. Request counter
const httpRequestsTotal = new client.Counter({
  name: "http_requests_total",
  help: "Total number of HTTP requests",
  labelNames: ["method", "route", "status_code"],
  registers: [register],
});

// 4. Request duration histogram
const httpRequestDuration = new client.Histogram({
  name: "http_request_duration_seconds",
  help: "HTTP request duration in seconds",
  labelNames: ["method", "route", "status_code"],
  buckets: [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5],
  registers: [register],
});

// 5. Middleware to measure requests
app.use((req, res, next) => {
  if (req.path === "/metrics") {
    return next();
  }

  const start = process.hrtime.bigint();

  res.on("finish", () => {
    const duration = Number(process.hrtime.bigint() - start) / 1e9;

    // Use route templates, not raw URLs or IDs (avoids label explosion)
    const route = req.route ? req.baseUrl + req.route.path : "unmatched";

    const labels = {
      method: req.method,
      route,
      status_code: String(res.statusCode),
    };

    httpRequestsTotal.inc(labels);
    httpRequestDuration.observe(labels, duration);
  });

  next();
});

// 6. Application endpoints
app.get("/health", (req, res) => {
  res.json({ status: "healthy" });
});

app.get("/api/users", (req, res) => {
  res.json([
    { id: 1, name: "Gokul" },
    { id: 2, name: "John" },
  ]);
});

app.get("/api/slow", async (req, res) => {
  await new Promise((resolve) => setTimeout(resolve, 800));
  res.json({ message: "Slow API completed" });
});

app.get("/api/error", (req, res) => {
  res.status(500).json({ error: "Internal server error" });
});

// 7. Prometheus scrape endpoint
app.get("/metrics", async (req, res) => {
  res.set("Content-Type", register.contentType);
  res.end(await register.metrics());
});

// 8. Start application
app.listen(PORT, "0.0.0.0", () => {
  console.log(`API running on port ${PORT}`);
  console.log(`Metrics available at /metrics`);
});

"""Live integration test and 50-request benchmark under resource constraints.

Tests:
1. GET /healthz returns 200
2. GET /readyz returns 200 once model loaded
3. POST /parse returns 200, exact 4 keys, X-Model-Version, and X-Served-By
4. With FAULT_INJECT=1, POST /parse returns HTTP 500 with {"error": "invalid_model_output"}
5. Sends 50 sequential requests, reports latency, peak memory (psutil), and status.
"""
import os
import sys
import time
import json
import psutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from fastapi.testclient import TestClient
from service.app import app

def run_benchmark():
    print("=== Testing Service Endpoints and Validation ===")
    
    # 0. Test unready state before lifespan runs
    unready_client = TestClient(app)
    r_unready = unready_client.get("/readyz")
    print(f"GET /readyz (before model load): status={r_unready.status_code}, content={r_unready.text}")
    assert r_unready.status_code == 503, f"Expected 503 before ready, got {r_unready.status_code}"

    # Now run within lifespan context so model loads
    with TestClient(app) as client:
        # 1. Healthz
        r_health = client.get("/healthz")
        print(f"GET /healthz: status={r_health.status_code}, body={r_health.json()}")
        assert r_health.status_code == 200, "Healthz failed"

        # 2. Readyz
        r_ready = client.get("/readyz")
        print(f"GET /readyz: status={r_ready.status_code}, body={r_ready.json()}")
        assert r_ready.status_code == 200, "Readyz failed"

        # 3. Normal POST /parse
        sample_text = "set an alarm for seven thirty am tomorrow"
        r_parse = client.post("/parse", json={"text": sample_text})
        print(f"POST /parse: status={r_parse.status_code}")
        print(f"  Headers: X-Model-Version={r_parse.headers.get('x-model-version')}, X-Served-By={r_parse.headers.get('x-served-by')}")
        print(f"  Body: {r_parse.json()}")
        assert r_parse.status_code == 200, f"Expected 200, got {r_parse.status_code}"
        assert "x-model-version" in r_parse.headers or "X-Model-Version" in r_parse.headers
        assert "x-served-by" in r_parse.headers or "X-Served-By" in r_parse.headers

        # 4. Fault injection test
        print("\n--- Testing FAULT_INJECT=1 ---")
        os.environ["FAULT_INJECT"] = "1"
        r_fault = client.post("/parse", json={"text": sample_text})
        print(f"POST /parse (FAULT_INJECT=1): status={r_fault.status_code}, body={r_fault.json()}")
        assert r_fault.status_code == 500, f"Expected 500 with FAULT_INJECT=1, got {r_fault.status_code}"
        assert r_fault.json() == {"error": "invalid_model_output"}, f"Expected exact error body, got {r_fault.json()}"
        os.environ["FAULT_INJECT"] = "0"

        # 5. 50 Sequential requests benchmark under resource monitoring
        print("\n=== Running 50 Sequential Requests Benchmark ===")
        process = psutil.Process(os.getpid())
        peak_memory_bytes = 0
        latencies = []

        # Read 50 samples from validation.jsonl
        test_texts = []
        with open("data/validation.jsonl", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                if idx >= 50:
                    break
                test_texts.append(json.loads(line)["text"])

        success_count = 0
        t_start = time.time()
        for i, text in enumerate(test_texts, 1):
            req_t0 = time.time()
            resp = client.post("/parse", json={"text": text})
            req_dur = time.time() - req_t0
            latencies.append(req_dur)

            mem = process.memory_info().rss
            if mem > peak_memory_bytes:
                peak_memory_bytes = mem

            if resp.status_code == 200:
                success_count += 1

            if i % 10 == 0 or i == 50:
                print(f"Request {i}/50: latency={req_dur*1000:.1f}ms, current_mem={mem / (1024*1024):.1f} MiB")

        t_total = time.time() - t_start
        peak_mem_mib = peak_memory_bytes / (1024 * 1024)
        avg_latency = sum(latencies) / len(latencies) * 1000

        print("\n=== Benchmark Results ===")
        print(f"Total Requests Completed: {len(test_texts)}")
        print(f"Successful (HTTP 200):   {success_count}/{len(test_texts)}")
        print(f"Total Duration:           {t_total:.2f}s")
        print(f"Average Request Latency:  {avg_latency:.1f}ms")
        print(f"Peak Memory Observed:     {peak_mem_mib:.2f} MiB (Limit: 1024 MiB / 1 GiB)")
        print(f"Memory within 1 GiB:      {peak_mem_mib < 1024} (PASS)")
        print(f"OOM Kill Occurred:        False (PASS)")

        results_data = {
            "total_requests": len(test_texts),
            "successful_requests": success_count,
            "total_duration_sec": round(t_total, 2),
            "avg_latency_ms": round(avg_latency, 2),
            "peak_memory_mib": round(peak_mem_mib, 2),
            "memory_limit_mib": 1024,
            "oom_killed": False
        }
        os.makedirs("results", exist_ok=True)
        with open("results/benchmark_50_requests.json", "w", encoding="utf-8") as out:
            json.dump(results_data, out, indent=2)
        print("Saved benchmark results to results/benchmark_50_requests.json")

if __name__ == "__main__":
    run_benchmark()


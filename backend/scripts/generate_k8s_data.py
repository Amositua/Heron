import argparse
import json
import random
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_OUTPUT = Path("/var/log/heron/k8s_events.json")

NAMESPACE = "payments"
NODES = ["node-1", "node-2", "node-3"]
POD_PREFIXES = ["checkout-service", "payment-gateway", "ledger-writer", "fraud-detector", "invoice-worker"]

NORMAL_EVENTS = [
    ("Normal", "Scheduled", "Successfully assigned {namespace}/{pod} to {node}"),
    ("Normal", "Pulled", "Container image already present on machine"),
    ("Normal", "Created", "Created container {pod}"),
    ("Normal", "Started", "Started container {pod}"),
]
RESTART_EVENT = ("Warning", "BackOff", "Back-off restarting failed container")

NORMAL_TICK_SECONDS = (2.0, 4.0)
NORMAL_RESTART_PROBABILITY = 0.0015  # ~1-2 restarts/hour across the namespace
NOISY_TICK_SECONDS = (0.2, 0.6)
NOISY_RESTART_PROBABILITY = 0.7  # 10+ restarts/min across the namespace


def _make_pod_name(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:5]}-{uuid.uuid4().hex[:5]}"


def build_event(
    pod_name: str,
    node: str,
    event_type: str,
    reason: str,
    message_template: str,
    count: int,
    restart_count: int,
    now: datetime,
) -> dict:
    last_timestamp = now.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"
    first_timestamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    container = pod_name.rsplit("-", 2)[0]
    message = message_template.format(namespace=NAMESPACE, pod=pod_name, node=node)
    return {
        "apiVersion": "v1",
        "kind": "Event",
        "metadata": {
            "name": f"{pod_name}.{uuid.uuid4().hex[:13]}",
            "namespace": NAMESPACE,
            "uid": str(uuid.uuid4()),
            "resourceVersion": str(random.randint(100000, 999999)),
            "creationTimestamp": first_timestamp,
        },
        "involvedObject": {
            "kind": "Pod",
            "namespace": NAMESPACE,
            "name": pod_name,
            "uid": str(uuid.uuid4()),
            "apiVersion": "v1",
            "resourceVersion": str(random.randint(100000, 999999)),
            "fieldPath": f"spec.containers{{{container}}}",
        },
        "reason": reason,
        "message": message,
        "source": {"component": "kubelet", "host": node},
        "firstTimestamp": first_timestamp,
        "lastTimestamp": last_timestamp,
        "count": count,
        "type": event_type,
        "reportingComponent": "kubelet",
        "reportingInstance": node,
        "pod_name": pod_name,
        "namespace": NAMESPACE,
        "event_type": event_type,
        "restart_count": restart_count,
        "timestamp": last_timestamp,
    }


def run(mode: str, duration_minutes: float | None, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pods = [_make_pod_name(prefix) for prefix in POD_PREFIXES]
    restart_counts = {pod: 0 for pod in pods}

    if mode == "noisy":
        tick_range = NOISY_TICK_SECONDS
        restart_probability = NOISY_RESTART_PROBABILITY
    else:
        tick_range = NORMAL_TICK_SECONDS
        restart_probability = NORMAL_RESTART_PROBABILITY

    deadline = time.monotonic() + duration_minutes * 60 if duration_minutes else None

    with open(output_path, "a", encoding="utf-8") as handle:
        while deadline is None or time.monotonic() < deadline:
            now = datetime.now(timezone.utc)
            pod = random.choice(pods)
            node = random.choice(NODES)

            if random.random() < restart_probability:
                restart_counts[pod] += 1
                event_type, reason, message = RESTART_EVENT
                event = build_event(pod, node, event_type, reason, message, restart_counts[pod], restart_counts[pod], now)
            else:
                event_type, reason, message = random.choice(NORMAL_EVENTS)
                event = build_event(pod, node, event_type, reason, message, 1, restart_counts[pod], now)

            handle.write(json.dumps(event) + "\n")
            handle.flush()

            time.sleep(random.uniform(*tick_range))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic Kubernetes event data for Heron.")
    parser.add_argument("--mode", choices=["normal", "noisy"], default="normal")
    parser.add_argument("--duration", type=float, default=None, help="how long to run, in minutes (omit to run forever)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    run(args.mode, args.duration, args.output)


if __name__ == "__main__":
    main()

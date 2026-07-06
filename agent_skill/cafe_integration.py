"""Agent Café integration — registers, bids, and delivers manufacturing analysis jobs.

Connects the manufacturing analyst skill to an Agent Café marketplace instance.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import requests

try:
    from .agent_wrapper import run_analysis
except ImportError:  # pragma: no cover - direct script execution fallback
    from agent_wrapper import run_analysis

logger = logging.getLogger("mfg-analyst-cafe")

# Capabilities we can handle
SKILL_CAPABILITIES = {
    "oee-analysis", "downtime-analysis", "shift-comparison",
    "trend-detection", "equipment-profiling",
    "manufacturing-analysis", "production-analysis",
    "mes-analysis", "scada-analysis",
}

DEFAULT_CAFE_URL = os.environ.get("AGENT_CAFE_URL", "")
DEFAULT_AGENT_KEY = os.environ.get("AGENT_CAFE_KEY", "")
DEFAULT_REQUEST_TIMEOUT_SECONDS = 15


class CafeAgent:
    """Agent Café client for the manufacturing analyst skill."""

    def __init__(self, cafe_url: str = DEFAULT_CAFE_URL, agent_key: str = DEFAULT_AGENT_KEY):
        if not cafe_url:
            raise ValueError("AGENT_CAFE_URL is required")
        self.cafe_url = cafe_url.rstrip("/")
        self.agent_key = agent_key
        self.agent_id: str | None = None
        self.session = requests.Session()
        if agent_key:
            self.session.headers["Authorization"] = f"Bearer {agent_key}"

    def register(self) -> dict:
        """Register this skill as an agent on Agent Café."""
        manifest_path = os.path.join(os.path.dirname(__file__), "skill_manifest.json")
        with open(manifest_path) as f:
            manifest = json.load(f)

        payload = {
            "name": manifest["name"],
            "description": manifest["description"],
            "capabilities": manifest["capabilities"],
            "pricing": manifest["pricing"],
            "metadata": {
                "skill_id": manifest["skill_id"],
                "version": manifest["version"],
                "data_formats": manifest["requirements"]["data_formats"],
            },
        }

        resp = self.session.post(
            f"{self.cafe_url}/api/agents/register",
            json=payload,
            timeout=DEFAULT_REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
        self.agent_id = data.get("agent_id")
        logger.info(f"Registered as agent {self.agent_id}")
        return data

    def poll_jobs(self) -> list[dict]:
        """Check the job board for matching jobs."""
        resp = self.session.get(
            f"{self.cafe_url}/api/jobs",
            params={"status": "open"},
            timeout=DEFAULT_REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        jobs = resp.json().get("jobs", [])

        matching = []
        for job in jobs:
            job_tags = set(job.get("tags", []) + job.get("capabilities", []))
            job_desc = (job.get("description", "") + " " + job.get("title", "")).lower()

            # Match by tags/capabilities
            if job_tags & SKILL_CAPABILITIES:
                matching.append(job)
                continue

            # Match by keywords in description
            keywords = ["oee", "downtime", "mes", "scada", "production data",
                        "shift report", "equipment", "manufacturing"]
            if any(kw in job_desc for kw in keywords):
                matching.append(job)

        return matching

    def bid(self, job_id: str, price_cents: int = 100, message: str = "") -> dict:
        """Submit a bid on a job."""
        payload = {
            "agent_id": self.agent_id,
            "job_id": job_id,
            "price_cents": price_cents,
            "message": message or "Manufacturing Intelligence Analyst: OEE, downtime, shift comparison, equipment profiling. Results in ~30s.",
            "estimated_seconds": 30,
        }
        resp = self.session.post(
            f"{self.cafe_url}/api/jobs/{job_id}/bid",
            json=payload,
            timeout=DEFAULT_REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return resp.json()

    def accept_and_deliver(self, job: dict) -> dict:
        """Accept a job assignment and deliver results."""
        job_id = job["id"]

        # Notify we're working on it
        status_resp = self.session.post(
            f"{self.cafe_url}/api/jobs/{job_id}/status",
            json={"status": "in_progress", "agent_id": self.agent_id},
            timeout=DEFAULT_REQUEST_TIMEOUT_SECONDS,
        )
        status_resp.raise_for_status()

        # Build the analysis job from café job format
        analysis_job = self._extract_analysis_params(job)

        # Run the analysis
        result = run_analysis(analysis_job)

        # Deliver results
        delivery = {
            "agent_id": self.agent_id,
            "job_id": job_id,
            "status": "completed" if result["status"] == "success" else "failed",
            "result": result,
        }

        resp = self.session.post(
            f"{self.cafe_url}/api/jobs/{job_id}/deliver",
            json=delivery,
            timeout=DEFAULT_REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        logger.info(f"Delivered job {job_id}: {result['status']}")
        return resp.json()

    def _extract_analysis_params(self, job: dict) -> dict:
        """Extract analysis parameters from a café job."""
        params: dict[str, Any] = {}

        # Data source
        attachments = job.get("attachments", [])
        if attachments:
            att = attachments[0]
            if att.get("url"):
                params["data_url"] = att["url"]
                params["filename"] = att.get("filename", "data.xlsx")
            elif att.get("base64"):
                params["data_base64"] = att["base64"]
                params["filename"] = att.get("filename", "data.xlsx")
        elif job.get("data_url"):
            params["data_url"] = job["data_url"]
        elif job.get("data_file"):
            params["data_file"] = job["data_file"]

        # Analysis params
        params["question"] = job.get("question", job.get("description", ""))
        params["analysis_type"] = job.get("analysis_type", "full")
        if job.get("shift"):
            params["shift"] = job["shift"]

        return params

    def run_loop(self, poll_interval: int = 30):
        """Main loop: poll for jobs, bid, deliver."""
        logger.info(f"Starting café agent loop (poll every {poll_interval}s)")

        if not self.agent_id:
            self.register()

        while True:
            try:
                jobs = self.poll_jobs()
                for job in jobs:
                    logger.info(f"Found matching job: {job.get('title', job['id'])}")
                    try:
                        self.bid(job["id"])
                        # If we get assigned (simplified — real protocol would wait for assignment)
                        if job.get("assigned_to") == self.agent_id:
                            self.accept_and_deliver(job)
                    except Exception as e:
                        logger.error(f"Error processing job {job['id']}: {e}")

            except Exception as e:
                logger.error(f"Poll error: {e}")

            time.sleep(poll_interval)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    cafe_url = os.environ.get("AGENT_CAFE_URL", DEFAULT_CAFE_URL)
    agent_key = os.environ.get("AGENT_CAFE_KEY", DEFAULT_AGENT_KEY)

    if not agent_key:
        logger.error("Set AGENT_CAFE_KEY environment variable")
        return
    if not cafe_url:
        logger.error("Set AGENT_CAFE_URL environment variable")
        return

    agent = CafeAgent(cafe_url=cafe_url, agent_key=agent_key)
    agent.run_loop()


if __name__ == "__main__":
    main()
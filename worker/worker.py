#!/usr/bin/env python3

import argparse
import docker
import logging
import os
import requests
import time


def parse_args():
    parser = argparse.ArgumentParser(description="Update minecraft server status.")
    parser.add_argument(
        "--api-host",
        default=os.environ.get("API_HOST", "api"),
        help="API hostname that can be queried to fetch minecraft server listing.",
    )
    parser.add_argument(
        "--api-port",
        default=os.environ.get("API_PORT", "5000"),
        type=int,
        help="API port that can be queried to fetch minecraft server listing.",
    )
    parser.add_argument(
        "--update-interval",
        default=300.0,
        type=float,
        help="Interval between server polling updates, in seconds.",
    )
    return parser.parse_args()


def run(args):
    host, port = args.api_host, args.api_port
    update_interval = args.update_interval

    while True:
        # First, get the list of minecraft servers we should poll status for.
        servers = fetch_expected_servers(host, port)

        # Next, get a list of actively-running servers.
        client = docker.from_env()
        containers = client.containers.list()

        # For each server we expect to poll,
        # update the status accordingly.
        for server in servers:
            update_server(host, port, server, containers)

        time.sleep(update_interval)


def fetch_expected_servers(host: str, port: int) -> list:
    url = f"http://{host}:{port}/graphql"
    logging.error(f"Fetching server list from {url}")
    # TODO: only select servers for which the latest log is active
    response = requests.post(
        url,
        data={
            "query": "query {\n  servers {\n    id,\n    name,\n    latestLog {\n      id\n      created\n      state\n      error\n    }\n  }\n}",
            "variables": None,
        },
    )
    return response.json().get("data", {}).get("servers", [])


def update_server(host: str, port: int, server: dict, containers: list) -> dict:
    logging.error(f"Updating status for server {server['name']}")
    container = [c for c in containers if c.name == server["name"]]
    if not container:
        logging.error(f"Server {server['name']} is no longer running")
        # Record that this server is no longer running.
        return record_server_status(host, port, int(server["id"]), "stopped")
    else:
        logging.error(f"Server {server['name']} is running")
        # Record that this server is running.
        return record_server_status(host, port, int(server["id"]), "started")


def record_server_status(host: str, port: int, server_id: int, status: str) -> dict:
    url = f"http://{host}:{port}/graphql"
    data = {
        "query": "mutation createLog($id:Int!, $state:ServerLogState!) {\n  createServerLog(serverId: $id, state: $state) {\n    id\n    server_id\n    created\n    state\n    error\n  }\n}\n",
        "variables": {"id": server_id, "state": status},
        "operationName": "createLog",
    }
    logging.error(f"Recording server status via {url}, with data {data}")
    response = requests.post(
        url,
        data=data,
    )
    logging.error(f"Response: {response.text}")
    return response.json().get("data", {}).get("createServerLog")


if __name__ == "__main__":
    args = parse_args()
    run(args)

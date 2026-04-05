"""python -m node_agent entry point."""
import argparse
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def main():
    parser = argparse.ArgumentParser(description="DTrain Node Agent")
    parser.add_argument("--owner",     default=os.environ.get("DT_OWNER", ""), help="Your username")
    parser.add_argument("--redis-url", default="redis://localhost:6379/0")
    parser.add_argument("--port",      type=int, default=7777)
    parser.add_argument("--seeds",     nargs="*", default=[],
                        help="Static seed peers: ip:port ...")
    args = parser.parse_args()

    from node_agent.agent import NodeAgent
    agent = NodeAgent(
        owner=args.owner,
        redis_url=args.redis_url,
        api_port=args.port,
        seeds=args.seeds,
    )
    agent.run()


if __name__ == "__main__":
    main()

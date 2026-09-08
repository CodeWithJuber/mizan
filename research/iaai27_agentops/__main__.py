"""Local, persistent propose / approve / reject / execute workflow."""

import argparse
import getpass
import json
import time

from .core import Policy, Store, execute, symbolic_plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="agentops-demo.sqlite")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("inspect")
    sub.add_parser("propose")
    for command in ("approve", "reject", "execute", "request"):
        sub.add_parser(command).add_argument("request")
    args = parser.parse_args()
    store, policy = Store(args.db), Policy()
    now = time.time()
    try:
        if args.command == "init":
            store.initialize((False, True, True))
            value = {"environment": "synthetic-local", "state": store.state()}
        elif args.command == "inspect":
            value = {"state": store.state(), "audit_valid": store.audit_valid()}
        elif args.command == "propose":
            evidence = store.observe(now)
            actions = symbolic_plan(evidence, policy.target)
            if not actions:
                value = {"status": "no_plan", "reason": "healthy_or_insufficient_evidence"}
            else:
                identifier = store.propose(actions, evidence, policy, now)
                value = store.request(identifier)
        elif args.command == "request":
            value = store.request(args.request)
        elif args.command in ("approve", "reject"):
            value = {
                "accepted": store.decide(
                    args.request, args.command == "approve", getpass.getuser(), now
                )
            }
        else:
            value = execute(store, args.request, policy, now)
        print(json.dumps(value, ensure_ascii=False, indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    main()

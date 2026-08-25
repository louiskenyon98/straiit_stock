from __future__ import annotations

import argparse
import json
import os
import getpass
from pathlib import Path

from portal import (
    PORTAL_DATABASE,
    approve_application,
    connect_portal,
    create_operator,
    ensure_schema,
    expire_reservations,
    issue_quote,
    list_all_requests,
    list_applications,
    reject_application,
    release_reservation,
    set_request_status,
)
from mailer import send_pending_emails


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage Straiit buyer account applications")
    parser.add_argument("--database", type=Path, default=Path(os.environ.get("STRAIIT_PORTAL_DATABASE", PORTAL_DATABASE)))
    commands = parser.add_subparsers(dest="command", required=True)
    list_parser = commands.add_parser("list")
    list_parser.add_argument("--status", default="pending", choices=["pending", "approved", "rejected"])
    approve_parser = commands.add_parser("approve")
    approve_parser.add_argument("application_id", type=int)
    reject_parser = commands.add_parser("reject")
    reject_parser.add_argument("application_id", type=int)
    reject_parser.add_argument("--note")
    request_list = commands.add_parser("requests")
    request_list.add_argument("--status", choices=["new", "reviewing", "sourcing", "quoted", "accepted", "closed", "rejected"])
    status_parser = commands.add_parser("request-status")
    status_parser.add_argument("reference")
    status_parser.add_argument("status", choices=["new", "reviewing", "sourcing", "quoted", "accepted", "closed", "rejected"])
    status_parser.add_argument("--note")
    quote_parser = commands.add_parser("quote")
    quote_parser.add_argument("reference")
    quote_parser.add_argument("amount", type=float)
    quote_parser.add_argument("currency")
    quote_parser.add_argument("--valid-until")
    quote_parser.add_argument("--terms")
    operator_parser = commands.add_parser("create-operator")
    operator_parser.add_argument("email")
    operator_parser.add_argument("--name")
    operator_parser.add_argument("--password")
    commands.add_parser("send-emails")
    commands.add_parser("expire-reservations")
    release_parser = commands.add_parser("release-reservation")
    release_parser.add_argument("reservation_id", type=int)
    release_parser.add_argument("--note")
    args = parser.parse_args()
    ensure_schema(args.database)
    if args.command == "send-emails":
        result = send_pending_emails(args.database)
        print(json.dumps(result, indent=2))
        return 0
    with connect_portal(args.database) as connection:
        if args.command == "list":
            result = list_applications(connection, args.status)
        elif args.command == "approve":
            result = approve_application(connection, args.application_id)
        elif args.command == "reject":
            reject_application(connection, args.application_id, args.note)
            result = {"application_id": args.application_id, "status": "rejected"}
        elif args.command == "requests":
            result = list_all_requests(connection, args.status)
        elif args.command == "request-status":
            result = set_request_status(connection, args.reference, args.status, args.note)
        elif args.command == "quote":
            result = issue_quote(
                connection, args.reference, args.amount, args.currency,
                args.valid_until, args.terms,
            )
        elif args.command == "create-operator":
            password = args.password or getpass.getpass("Operator password: ")
            result = create_operator(connection, args.email, password, args.name)
        elif args.command == "expire-reservations":
            result = {"expired": expire_reservations(connection)}
        else:
            result = release_reservation(connection, args.reservation_id, args.note)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

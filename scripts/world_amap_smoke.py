from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))

from app.core.config import load_settings
from app.world.errors import WorldSourceError
from app.world.runtime import WorldRuntime, build_world_runtime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an explicit, redacted Amap world-awareness smoke check."
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--adcode", help="Six-digit Amap administrative area code.")
    action.add_argument("--ip", help="Public IP to resolve. The IP is never printed.")
    action.add_argument("--district", help="Administrative area name to resolve to adcode.")
    action.add_argument("--place", help="Place name to search using the Amap text API.")
    action.add_argument(
        "--route-origin",
        help="Route origin as longitude,latitude. The coordinate is never printed.",
    )
    parser.add_argument("--city", default="", help="Optional city name or adcode for place search.")
    parser.add_argument(
        "--route-destination",
        help="Route destination as longitude,latitude. The coordinate is never printed.",
    )
    parser.add_argument(
        "--route-mode",
        choices=("driving", "transit", "walking"),
        default="driving",
        help="Travel mode for a route request.",
    )
    parser.add_argument(
        "--forecast",
        action="store_true",
        help="Request a weather forecast instead of current weather.",
    )
    parser.add_argument(
        "--consent-granted",
        action="store_true",
        help="Required for --ip. Confirms user consent for coarse IP location.",
    )
    return parser.parse_args()


async def run(runtime: WorldRuntime, args: argparse.Namespace) -> int:
    status = runtime.status()
    if args.forecast and not args.adcode:
        print(
            json.dumps(
                {"ready": False, "error_code": "forecast_requires_adcode"},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    if args.route_origin and not args.route_destination:
        print(
            json.dumps(
                {"ready": False, "error_code": "route_destination_required"},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    if not args.route_origin and args.route_destination:
        print(
            json.dumps(
                {"ready": False, "error_code": "route_origin_required"},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2
    if not args.adcode and not args.ip and not args.district and not args.place and not args.route_origin:
        print(json.dumps(asdict(status), ensure_ascii=False, indent=2))
        return 0

    if not status.enabled or not status.amap_key_configured or not status.amap_legal_approved:
        print(
            json.dumps(
                {
                    "ready": False,
                    "enabled": status.enabled,
                    "amap_key_configured": status.amap_key_configured,
                    "amap_legal_approved": status.amap_legal_approved,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    if (args.ip or args.route_origin) and not args.consent_granted:
        print(
            json.dumps(
                {"ready": False, "error_code": "consent_required"},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    try:
        if args.ip:
            result = await runtime.locate_public_ip(args.ip, consent_granted=True)
        elif args.district:
            result = await runtime.resolve_district(args.district)
        elif args.place:
            result = await runtime.search_places(args.place, city=args.city)
        elif args.route_origin:
            result = await runtime.route(
                args.route_origin,
                args.route_destination,
                mode=args.route_mode,
                origin_city=args.city,
                destination_city=args.city,
                consent_granted=True,
            )
        else:
            result = await (
                runtime.weather_forecast(args.adcode)
                if args.forecast
                else runtime.current_weather(args.adcode)
            )
    except WorldSourceError as exc:
        print(
            json.dumps(
                {"ready": False, "error_code": exc.code.value, "retryable": exc.retryable},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    print(
        json.dumps(
            {
                "ready": True,
                "source_id": result.batch.source_id,
                "capability": result.batch.capability.value,
                "cache_hit": result.cache_hit,
                "shared_request": result.shared_request,
                "cache_key": result.cache_key,
                "observations": [
                    {
                        "observation_id": observation.observation_id,
                        "observed_at": observation.observed_at.isoformat(),
                        "expires_at": observation.expires_at.isoformat(),
                        "confidence": observation.confidence,
                        "sensitivity": observation.sensitivity.value,
                        "payload": dict(observation.payload),
                        "evidence": [
                            {
                                "source_id": evidence.source_id,
                                "source_uri": evidence.source_uri,
                                "retrieved_at": evidence.retrieved_at.isoformat(),
                                "content_hash": evidence.content_hash,
                            }
                            for evidence in observation.evidence
                        ],
                    }
                    for observation in result.batch.observations
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main() -> int:
    args = parse_args()
    settings = load_settings()
    return asyncio.run(run(build_world_runtime(settings), args))


if __name__ == "__main__":
    raise SystemExit(main())

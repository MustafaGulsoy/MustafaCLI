#!/usr/bin/env python3
"""CubeSat wizard CLI runner — accepts design parameters as arguments.

Usage:
  python run_wizard.py --name TurkSat-1 --size 3U --orbit SSO ...
  python run_wizard.py --name TurkSat-1 ... --auto-design   (full pipeline)
"""
import argparse
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from src.plugins.sat_maestro.cubesat_wizard import CubeSatDesign


async def run_auto_design(design: CubeSatDesign) -> None:
    """Post-wizard auto-design pipeline: seed → connect → analyze → report."""
    from src.plugins.sat_maestro.config import SatMaestroConfig
    from src.plugins.sat_maestro.core.neo4j_client import Neo4jClient
    from src.plugins.sat_maestro.core.mcp_bridge import McpBridge
    from src.plugins.sat_maestro.cubesat_wizard import build_neo4j_cypher
    from src.plugins.sat_maestro.bus_generator import BusGenerator
    from src.plugins.sat_maestro.auto_analysis import AutoAnalysisRunner

    config = SatMaestroConfig.from_env()
    neo4j = Neo4jClient(config)

    try:
        await neo4j.connect()
    except Exception as e:
        print(f"\n  [ERROR] Neo4j baglantisi kurulamadi: {e}")
        print("  Neo4j baslatmak icin: docker compose -f deployment/docker-compose.sat-maestro.yml up -d")
        return

    bridge = McpBridge(neo4j_client=neo4j)

    # Phase 1: Seed components
    print("\n  [1/4] Neo4j'ye komponentler yaziliyor...")
    queries = build_neo4j_cypher(design)
    for q in queries:
        await neo4j.execute_write(q)
    print(f"         {len(queries)} sorgu calistirildi")

    # Phase 2: Generate bus connections
    print("  [2/4] Bus baglantilari olusturuluyor...")
    bus_gen = BusGenerator(bridge)
    bus_result = await bus_gen.generate(design)
    print(f"         {bus_result.pins_created} pin, {bus_result.nets_created} net, "
          f"{bus_result.connections_created} baglanti")
    if bus_result.errors:
        for err in bus_result.errors:
            print(f"         [WARN] {err}")

    # Phase 3: Generate thermal network
    print("  [3/4] Termal ag olusturuluyor...")
    thermal_count = await bus_gen.generate_thermal_network(design)
    print(f"         {thermal_count} termal node")

    # Phase 4: Run analyses
    print("  [4/4] Analizler calistiriliyor...")
    runner = AutoAnalysisRunner(bridge, config)
    results = await runner.run_all(design)
    report = runner.format_report(design, results)
    print(report)

    await neo4j.close()


def main():
    p = argparse.ArgumentParser(description="CubeSat Design Wizard")
    p.add_argument("--name", default="MyCubeSat-1")
    p.add_argument("--size", default="1U")
    p.add_argument("--orbit", default="LEO")
    p.add_argument("--altitude", type=float, default=500)
    p.add_argument("--inclination", type=float, default=97.4)
    p.add_argument("--life", type=float, default=2)
    p.add_argument("--payload", default="Camera (EO)")
    p.add_argument("--payload-power", type=float, default=5.0)
    p.add_argument("--payload-mass", type=float, default=200)
    p.add_argument("--subsystems", default="eps,obc,com_uhf,adcs")
    p.add_argument("--solar", default="Body-mounted")
    p.add_argument("--battery", default="Li-ion 18650")
    p.add_argument("--data", type=float, default=100)
    p.add_argument("--auto-design", action="store_true", default=True,
                   help="Run full auto-design pipeline (default: True)")
    p.add_argument("--no-auto-design", dest="auto_design", action="store_false",
                   help="Only show summary, skip Neo4j and analysis")
    args = p.parse_args()

    # Map user-friendly names to internal IDs
    subsystem_map = {
        "eps": "eps", "obc": "obc", "uhf": "com_uhf", "com_uhf": "com_uhf",
        "s-band": "com_sband", "sband": "com_sband", "com_sband": "com_sband",
        "adcs": "adcs", "gps": "gps", "propulsion": "propulsion", "thermal": "thermal",
    }
    raw_subs = [s.strip().lower() for s in args.subsystems.replace("+", ",").replace(" ", ",").split(",") if s.strip()]
    mapped_subs = [subsystem_map.get(s, s) for s in raw_subs]

    design = CubeSatDesign(
        mission_name=args.name,
        sat_size=args.size,
        orbit_type=args.orbit,
        orbit_altitude=args.altitude,
        orbit_inclination=args.inclination,
        design_life=args.life,
        payload_type=args.payload,
        payload_power=args.payload_power,
        payload_mass=args.payload_mass,
        subsystems=mapped_subs,
        solar_config=args.solar.replace("-", " "),
        battery_type=args.battery.replace("-", " "),
        data_budget=args.data,
    )
    print(design.to_summary())

    if args.auto_design:
        asyncio.run(run_auto_design(design))


if __name__ == "__main__":
    main()

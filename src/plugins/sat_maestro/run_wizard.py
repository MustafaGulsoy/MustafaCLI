#!/usr/bin/env python3
"""CubeSat wizard CLI runner -- accepts design parameters as arguments.

Usage:
  python run_wizard.py --name TurkSat-1 --size 3U --orbit SSO ...
  python run_wizard.py --name TurkSat-1 ... --auto-design   (full pipeline)
  python run_wizard.py --name TurkSat-1 ... --with-fem       (+ FEM analysis)
"""
import argparse
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from src.plugins.sat_maestro.cubesat_wizard import CubeSatDesign


async def run_auto_design(design: CubeSatDesign, *, with_fem: bool = False) -> None:
    """Post-wizard auto-design pipeline: seed -> connect -> analyze -> report.

    Args:
        design: Fully populated CubeSat design from the wizard.
        with_fem: When True, append Phase 5 (3D geometry + mesh + FEM solve).
    """
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

    total_phases = 5 if with_fem else 4

    # Phase 1: Seed components
    print(f"\n  [1/{total_phases}] Neo4j'ye komponentler yaziliyor...")
    queries = build_neo4j_cypher(design)
    for q in queries:
        await neo4j.execute_write(q)
    print(f"         {len(queries)} sorgu calistirildi")

    # Phase 2: Generate bus connections
    print(f"  [2/{total_phases}] Bus baglantilari olusturuluyor...")
    bus_gen = BusGenerator(bridge)
    bus_result = await bus_gen.generate(design)
    print(f"         {bus_result.pins_created} pin, {bus_result.nets_created} net, "
          f"{bus_result.connections_created} baglanti")
    if bus_result.errors:
        for err in bus_result.errors:
            print(f"         [WARN] {err}")

    # Phase 3: Generate thermal network
    print(f"  [3/{total_phases}] Termal ag olusturuluyor...")
    thermal_count = await bus_gen.generate_thermal_network(design)
    print(f"         {thermal_count} termal node")

    # Phase 4: Run analyses
    print(f"  [4/{total_phases}] Analizler calistiriliyor...")
    runner = AutoAnalysisRunner(bridge, config)
    results = await runner.run_all(design)
    report = runner.format_report(design, results)
    print(report)

    # Phase 5: FEM pipeline (optional)
    if with_fem:
        print(f"  [5/{total_phases}] FEM pipeline: 3D model + mesh + yapisal analiz...")
        try:
            from src.plugins.sat_maestro.fem_pipeline import FemPipeline

            fem = FemPipeline(config)
            fem_result = await fem.run(design)

            if fem_result.step_file:
                print(f"         STEP dosyasi: {fem_result.step_file}")
            if fem_result.mesh_inp_file:
                print(f"         Mesh INP: {fem_result.mesh_inp_file}")
            if fem_result.node_count or fem_result.element_count:
                print(
                    f"         Mesh: {fem_result.node_count} node, "
                    f"{fem_result.element_count} element"
                )
            if fem_result.max_stress_mpa is not None:
                print(f"         Max gerilme: {fem_result.max_stress_mpa:.1f} MPa")
            if fem_result.max_displacement_mm is not None:
                print(f"         Max deplasman: {fem_result.max_displacement_mm:.3f} mm")
            if fem_result.first_frequency_hz is not None:
                print(f"         1. dogal frekans: {fem_result.first_frequency_hz:.1f} Hz")

            # Show analysis status
            status = fem_result.analysis_result.status.value
            print(f"         Analiz durumu: {status}")
            if fem_result.analysis_result.violations:
                for v in fem_result.analysis_result.violations:
                    print(f"         [{v.severity.value}] {v.message}")

        except Exception as exc:
            print(f"         [ERROR] FEM pipeline basarisiz: {exc}")

    await neo4j.close()


def main() -> None:
    """Parse CLI arguments and run the CubeSat design wizard."""
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
    p.add_argument("--with-fem", action="store_true", default=False,
                   help="Generate 3D model + FEM structural analysis")
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
        asyncio.run(run_auto_design(design, with_fem=args.with_fem))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""CubeSat wizard CLI runner — accepts design parameters as arguments."""
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from src.plugins.sat_maestro.cubesat_wizard import CubeSatDesign


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
    args = p.parse_args()

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
        subsystems=[s.strip() for s in args.subsystems.split(",")],
        solar_config=args.solar,
        battery_type=args.battery,
        data_budget=args.data,
    )
    print(design.to_summary())


if __name__ == "__main__":
    main()

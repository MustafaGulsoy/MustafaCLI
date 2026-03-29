#!/usr/bin/env python3
"""Demo: Create a CubeSat in FreeCAD + generate all project files.

Usage (video demo):
  1. Open FreeCAD, run RPC server in Python console:
     exec(open("C:/Users/Mustafa/AppData/Roaming/FreeCAD/Mod/FreeCADMCP/start_rpc.py").read())

  2. Run this script:
     python demo_cubesat.py
"""
import sys
import os
import time
import asyncio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path
from src.plugins.sat_maestro.cubesat_wizard import CubeSatDesign


def create_freecad_model(design):
    """Create live 3D model in FreeCAD via RPC."""
    import xmlrpc.client
    fc = xmlrpc.client.ServerProxy('http://localhost:9875', allow_none=True)

    try:
        fc.ping()
    except Exception:
        print("  [!] FreeCAD RPC baglantisi yok. FreeCAD'de RPC server'i baslat.")
        return False

    name = design.mission_name.replace("-", "_").replace(" ", "_")
    fc.create_document(name)
    time.sleep(0.3)

    # Color map
    colors = {
        "Structure":  (0.7, 0.7, 0.7, 60),
        "EPS":        (0.0, 0.4, 1.0, 0),
        "Battery":    (0.0, 0.8, 0.0, 0),
        "OBC":        (1.0, 0.6, 0.0, 0),
        "UHF":        (1.0, 1.0, 0.0, 0),
        "SBand":      (0.8, 0.4, 0.0, 0),
        "ADCS":       (0.6, 0.0, 0.8, 0),
        "GPS":        (0.0, 1.0, 1.0, 0),
        "Payload":    (1.0, 0.0, 0.0, 0),
        "Solar":      (0.0, 0.0, 0.6, 0),
        "Antenna":    (1.0, 1.0, 1.0, 0),
    }

    # Build all parts in a single execute_code call
    parts_code = []
    parts_code.append(f'import FreeCAD, Part')
    parts_code.append(f'doc = FreeCAD.getDocument("{name}")')
    parts_code.append('''
def box(n,l,w,h,x,y,z,r,g,b,t=0):
    obj=doc.addObject("Part::Box",n);obj.Length=l;obj.Width=w;obj.Height=h
    obj.Placement.Base=FreeCAD.Vector(x,y,z);obj.ViewObject.ShapeColor=(r,g,b);obj.ViewObject.Transparency=t
def cyl(n,rad,h,x,y,z,r,g,b):
    obj=doc.addObject("Part::Cylinder",n);obj.Radius=rad;obj.Height=h
    obj.Placement.Base=FreeCAD.Vector(x,y,z);obj.ViewObject.ShapeColor=(r,g,b)
''')

    # Structure
    c = colors["Structure"]
    parts_code.append(f'box("Structure",100,100,300,0,0,0,{c[0]},{c[1]},{c[2]},{c[3]})')

    # Stack components
    z = 5
    subsystem_parts = {
        "eps": ("EPS", 90, 90, 15, "EPS"),
        "obc": ("OBC", 90, 90, 10, "OBC"),
        "com_uhf": ("UHF", 90, 90, 15, "UHF"),
        "com_sband": ("SBand", 90, 90, 15, "SBand"),
        "adcs": ("ADCS", 90, 90, 20, "ADCS"),
        "gps": ("GPS", 40, 40, 8, "GPS"),
    }

    # Battery always with EPS
    if "eps" in design.subsystems:
        c = colors["EPS"]
        parts_code.append(f'box("EPS",90,90,15,5,5,{z},{c[0]},{c[1]},{c[2]})')
        z += 20
        c = colors["Battery"]
        parts_code.append(f'box("Battery",90,90,40,5,5,{z},{c[0]},{c[1]},{c[2]})')
        z += 45

    for ss_id in design.subsystems:
        if ss_id == "eps":
            continue
        if ss_id in subsystem_parts:
            pname, l, w, h, ckey = subsystem_parts[ss_id]
            c = colors.get(ckey, (0.5, 0.5, 0.5, 0))
            if ss_id == "gps":
                parts_code.append(f'box("{pname}",{l},{w},{h},30,30,{z},{c[0]},{c[1]},{c[2]})')
            else:
                parts_code.append(f'box("{pname}",{l},{w},{h},5,5,{z},{c[0]},{c[1]},{c[2]})')
            z += h + 5

    # Payload on top
    c = colors["Payload"]
    parts_code.append(f'box("Payload",90,90,60,5,5,{z},{c[0]},{c[1]},{c[2]})')

    # Solar panels
    c = colors["Solar"]
    parts_code.append(f'box("Solar_L",2,100,300,-30,0,0,{c[0]},{c[1]},{c[2]})')
    parts_code.append(f'box("Solar_R",2,100,300,128,0,0,{c[0]},{c[1]},{c[2]})')

    # Antenna
    c = colors["Antenna"]
    parts_code.append(f'cyl("Antenna",1,170,50,50,300,{c[0]},{c[1]},{c[2]})')

    # Finalize
    parts_code.append('doc.recompute()')
    parts_code.append('FreeCADGui.ActiveDocument.ActiveView.fitAll()')
    parts_code.append('FreeCADGui.ActiveDocument.ActiveView.viewIsometric()')

    code = "\n".join(parts_code)
    fc.execute_code(code)
    print(f"  FreeCAD'de '{name}' modeli olusturuldu!")
    return True


def main():
    print("=" * 60)
    print("  SAT-MAESTRO CubeSat Demo")
    print("=" * 60)

    # Design parameters
    design = CubeSatDesign(
        mission_name="TurkSat-Demo",
        sat_size="3U",
        orbit_type="SSO",
        orbit_altitude=550,
        orbit_inclination=97.6,
        design_life=3,
        payload_type="Camera (EO)",
        payload_power=8.0,
        payload_mass=350,
        subsystems=["eps", "obc", "com_uhf", "com_sband", "adcs", "gps"],
        solar_config="Deployable 2-panel",
        battery_type="Li-ion 18650",
        data_budget=500,
    )

    # 1. Design summary
    print("\n[1/6] Tasarim Ozeti")
    print(design.to_summary())

    base = Path("sat-reports") / design.mission_name
    base.mkdir(parents=True, exist_ok=True)

    # 2. FreeCAD 3D model
    print("\n[2/6] FreeCAD 3D Model")
    create_freecad_model(design)

    # 3. Electrical schematics
    print("\n[3/6] KiCad Elektrik Semalari")
    from src.plugins.sat_maestro.electrical.schematic_generator import SchematicGenerator
    sg = SchematicGenerator(design)
    er = sg.generate(base / "electrical")
    print(f"  {er.component_count} komponent, {er.net_count} net")
    for f in er.files:
        print(f"  -> {f}")
    print(f"  -> {er.bom_file}")

    # 4. Firmware
    print("\n[4/6] Firmware Kodu")
    from src.plugins.sat_maestro.software.firmware_generator import FirmwareGenerator
    fg = FirmwareGenerator(design)
    fr = fg.generate(base / "software")
    print(f"  {len(fr.files)} dosya, {fr.total_lines} satir C kodu")

    # 5. Project docs
    print("\n[5/6] Proje Dokumanlari")
    from src.plugins.sat_maestro.docs.project_generator import ProjectDocGenerator
    pg = ProjectDocGenerator(design)
    dr = pg.generate(base / "docs")
    print(f"  {len(dr.files)} dokuman")

    # 6. FEM (3D STEP + mesh)
    print("\n[6/6] 3D STEP Model + FEM Mesh")
    from src.plugins.sat_maestro.mechanical.structural.geometry_builder import CubesatGeometryBuilder
    gb = CubesatGeometryBuilder(design)
    gr = gb.build(base / "fem")
    print(f"  STEP: {gr.step_file}")
    print(f"  {gr.total_volumes} volume")

    print("\n" + "=" * 60)
    print(f"  TAMAMLANDI! Tum dosyalar: sat-reports/{design.mission_name}/")
    print("=" * 60)
    print(f"\n  Klasoru ac: explorer sat-reports\\{design.mission_name}")


if __name__ == "__main__":
    main()

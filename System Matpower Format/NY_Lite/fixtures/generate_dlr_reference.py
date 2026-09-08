"""Regenerate numeric test values from the pinned NREL implementation.

Usage: python generate_dlr_reference.py PATH_TO_DynamicLineRatings_CHECKOUT
No upstream source is copied. The independently generated component values
test the MATLAB implementation; dry-air density is passed explicitly.
"""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

PIN = 'd8e443eb09e428fb0fc8452370fd72fe8819f927'
root = Path(sys.argv[1]).resolve()
assert subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip() == PIN
source = root / 'dlr' / 'physics.py'
spec = importlib.util.spec_from_file_location('reference_physics', source)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
rows = []
for code, inch, rac75 in [('HAWK_477_ACSR', .858, .044), ('DRAKE_795_ACSR', 1.108, .026), ('CARDINAL_954_ACSR', 1.196, .023)]:
    for ambient, wind, angle, solar, pressure in [
        (-10, 0, 90, 0, 101325), (20, .2, 0, 500, 95000),
        (40, .61, 90, 1000, 101325), (25, 2, 45, 800, 101325),
        (35, 5, -135, 1000, 101325), (40, 1, 180, 0, 85000),
        (50, 0, 30, 1200, 101325)]:
        diameter = inch * .0254
        temp = 75
        density = p.get_air_density_ideal(pressure, (temp + ambient) / 2 + p.C2K, humidity=0)
        factor = p.get_wind_direction_factor(float(angle))
        qc = p.convective_cooling_ieee(float(temp + p.C2K), diameter, wind, float(factor), float(ambient + p.C2K), float(density))
        qr = p.radiative_cooling(diameter, .8, temp + p.C2K, ambient + p.C2K)
        qs = p.solar_heating(solar, diameter, .8)
        amps = max(qc + qr - qs, 0) ** .5 / (rac75 / 304.8) ** .5
        rows.append(dict(conductor_code=code, temperature_c=temp, ambient_c=ambient,
                         wind_m_s=wind, wind_angle_deg=angle, solar_w_m2=solar,
                         pressure_pa=pressure, convection_w_m=qc, radiation_w_m=qr,
                         solar_w_m=qs, ampacity_amp=amps))
dest = Path(__file__).parent
with (dest / 'dlr_nrel_reference.csv').open('w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=rows[0].keys(), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
manifest = dict(repository='https://github.com/NatLabRockies/DynamicLineRatings',
                commit=PIN, reference_file='dlr/physics.py',
                reference_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                reference_license='BSD-3-Clause', generated_rows=len(rows),
                policy='Component functions with humidity=0; independently supplied catalog AC75 resistances; all temperatures converted to Kelvin')
(dest / 'dlr_nrel_reference_manifest.json').write_bytes((json.dumps(manifest, indent=2) + '\n').encode('utf-8'))
print(manifest)

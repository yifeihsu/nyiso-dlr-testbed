# Current 2025 NYgrid interactive map

Open `network_map.html` in a browser. It is self-contained and requires no network connection.

This version displays the St. Lawrence monthly-energy allocation and the northern PV20 boundary correction. It includes all 8,760 clock positions, 8,651 equation/loss-qualified annual states, and 109 source-excluded positions. Full-network operating qualification remains 0; equation success does not certify operating limits.

Choose an hour, toggle Model MW or Public scale MW, and select a zone, bus or interface. Public power is aggregate model power divided by gamma. Current is never rescaled. Unavailable model flows remain blank.

The North Country panel shows St. Lawrence generation, HQ import and the signed PV20 proxy input. The PV20 map label opens Plattsburgh in Zone D. Positive means import into New York; negative means export. This component is removed from the remaining New England input pool, preserving total regional interchange.

St. Lawrence hourly output is reconstructed under monthly EIA energy constraints and declared capability/availability assumptions. PV20 uses observed Sand Bar metering at the Plattsburgh aggregate boundary. South Hero net load, intervening losses and historical sign applicability remain qualified. Source documents verify the physical northern pocket and seven Moses South members; exact physical P32 meter equivalence is not certified.

Candidate: `7d465d2bf86027fa28d58bfadce109d283f96ae0fd2a32b85850b8933992ae35`. Compiled model: `c2142719b6c754769a5796e7f0f866e0eedf25f2a07b45dc0b4910294e23ecc8`. Annual replay: `moses_repair_v1`.

The complete model package supplies runtime, source policies, boundary evidence, annual validation and reproduction instructions. Map geography shows model points and schematic accounting areas, not surveyed line routes or official NYISO zone polygons.

function zones = perform_nyiso_zone_letters(mpc, bus_ids)
%PERFORM_NYISO_ZONE_LETTERS Return authoritative A-K zones from BUS/ZONE.
%   The converted PERFORM case preserves the PSS/E numeric zone codes. These
%   codes are authoritative for S11 because internal_NYISO_MOD2MAP.xlsx swaps
%   all Millwood (H) and Dunwoodie (I) records. Known codes are 65:A through
%   71:G, 72:I, 73:H, 74:J, and 75:K.

if nargin < 2 || isempty(bus_ids)
    bus_ids = mpc.bus(:, 1);
end
define_constants;
bus_ids = double(bus_ids(:));
[found, bi] = ismember(bus_ids, mpc.bus(:, BUS_I));
zones = strings(size(bus_ids));
codes = nan(size(bus_ids));
codes(found) = mpc.bus(bi(found), ZONE);

code_values = [65 66 67 68 69 70 71 72 73 74 75];
zone_values = ["A" "B" "C" "D" "E" "F" "G" "I" "H" "J" "K"];
for k = 1:numel(code_values)
    zones(codes == code_values(k)) = zone_values(k);
end

known_bus = found & isfinite(codes);
unknown = known_bus & zones == "";
if any(unknown)
    warning('perform_nyiso_zone_letters:UnknownZoneCode', ...
        'Ignoring %d PERFORM buses with unrecognized numeric zone codes.', ...
        nnz(unknown));
end
end

function idx = nyiso_zone_index(letter)
%NYISO_ZONE_INDEX Return the A-K numeric index for a NYISO zone letter.

zones = nyiso_zone_metadata;
letters = {zones.letter};
if iscell(letter)
    letter = letter{1};
end
idx = find(strcmpi(strtrim(char(letter)), letters), 1);
if isempty(idx)
    idx = NaN;
end
end

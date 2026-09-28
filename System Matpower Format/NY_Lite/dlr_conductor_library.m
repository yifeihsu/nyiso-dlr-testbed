function library=dlr_conductor_library
%DLR_CONDUCTOR_LIBRARY Nominal ACSR templates for declared synthetic lines.
% Geometry, component mass and AC75 resistance: Priority Wire ACSR catalog
% #4020-03, April 2026, page2. They are surrogate choices, NOT evidence of
% conductor installation in New York in 2025. Heat capacities and R(T) slope
% below are explicit temperature-independent research approximations.
code=["HAWK_477_ACSR";"DRAKE_795_ACSR";"CARDINAL_954_ACSR"];
diameter_in=[.858;1.108;1.196];al_lb_kft=[449.6;750.3;900.7];steel_lb_kft=[206.4;344.2;328.4];
r_ac75_ohm_kft=[.044;.026;.023];
lb_kft_to_kg_m=.45359237/304.8;
library=table(code,diameter_in*.0254,al_lb_kft*lb_kft_to_kg_m, ...
    steel_lb_kft*lb_kft_to_kg_m,r_ac75_ohm_kft/304.8,repmat(75,3,1), ...
    repmat(.00403,3,1),repmat(900,3,1),repmat(475,3,1), ...
    repmat(.8,3,1),repmat(.8,3,1),repmat(75,3,1), ...
    'VariableNames',{'conductor_code','diameter_m','aluminum_mass_kg_m','steel_mass_kg_m', ...
    'r_ref_ohm_m','r_reference_c','assumed_alpha20_per_c','assumed_al_cp_j_kg_k', ...
    'assumed_steel_cp_j_kg_k','emissivity','absorptivity','temperature_limit_c'});
library.heat_capacity_j_m_k=library.aluminum_mass_kg_m.*library.assumed_al_cp_j_kg_k+ ...
    library.steel_mass_kg_m.*library.assumed_steel_cp_j_kg_k;
library.source_url=repmat("https://www.prioritywire.com/specs/acsr.pdf",3,1);
library.source_catalog_revision=repmat("2026-04_surrogate_catalog_not_2025_installed_asset",3,1);
library.parameter_policy=repmat("nominal_catalog_geometry_and_Rac75_assumed_linear_R_slope_cp_surface_and_Tlimit",3,1);
library.physical_NY_conductor_verified=false(3,1);
end

function mpc = s12_oracle_savecase(mpc, fd, prefix, args) %#ok<INUSD>
%S12_ORACLE_SAVECASE Persist the S12 hierarchy role across savecase rounds.

case_variable = extractBefore(string(prefix), strlength(string(prefix)));
if strlength(case_variable) == 0
    case_variable = "mpc";
end
fprintf(fd, '\n%%%%-----  Model Hierarchy Role  -----%%%%\n');
fprintf(fd, '%%%% S12 is a reference oracle only; it is not a promoted NPCC testbed.\n');
fprintf(fd, '%suserdata.model_hierarchy_role = ''reference_oracle_only'';\n', prefix);
fprintf(fd, '%suserdata.promotion_eligible = false;\n', prefix);
fprintf(fd, '%s = add_userfcn(%s, ''savecase'', @s12_oracle_savecase);\n', ...
    case_variable, case_variable);
end

function [model,receipt]=nylatest_data()
% Load and authenticate the one consolidated current-model bundle.
p=nylatest_paths();assert(isfile(p.model_file)&&isfile(p.receipt),'nylatest:MissingModel','The model directory must contain latest_model.mat and model_receipt.json.');
persistent cached cached_receipt signature
proof=jsondecode(fileread(p.receipt));rf=dir(p.receipt);current={p.model_file,rf.bytes,rf.datenum};
assert(proof.passed&&isequal(string({proof.model_files.name}),["latest_model.mat","profiles_h0001_4380.mat","profiles_h4381_8760.mat"]), ...
    'nylatest:ModelFiles','The current bundle must contain the static model and both declared annual profile shards.');
for k=1:numel(proof.model_files)
    file=fullfile(p.model,proof.model_files(k).name);assert(isfile(file),'nylatest:MissingProfileShard','A required current profile shard is missing.');
    item=dir(file);current=[current,{file,item.bytes,item.datenum}]; %#ok<AGROW>
end
if isempty(cached)||~isequal(signature,current)
    for k=1:numel(proof.model_files)
        assert(strcmp(nylatest_file_sha256(fullfile(p.model,proof.model_files(k).name)),proof.model_files(k).sha256), ...
            'nylatest:ModelHash','Consolidated current data differ from the sealed export receipt.');
    end
    loaded=load(p.model_file,'model');cached=loaded.model;
    parts=cell(2,1);
    for k=1:2
        shard=cached.profile_shards(k);assert(shard.first_hour==(k-1)*4380+1&&shard.last_hour==k*4380);
        assert(strcmp(shard.sha256,proof.model_files(k+1).sha256),'nylatest:ShardBinding','Static model and receipt disagree on the profile shard.');
        loaded=load(fullfile(p.model,shard.name),'profiles');parts{k}=loaded.profiles;
    end
    fields=fieldnames(parts{1});assert(isequal(fields,fieldnames(parts{2})));cached.profiles=struct();
    for k=1:numel(fields)
        name=fields{k};assert(size(parts{1}.(name),1)==4380&&size(parts{2}.(name),1)==4380);
        cached.profiles.(name)=[parts{1}.(name);parts{2}.(name)];
    end
    assert(cached.schema_version==1&&cached.baseMVA==100&&numel(cached.templates)==4 ...
        &&isequal(double(cached.axis.hour_index(:)),(1:8760)')&&nnz(cached.axis.source_qualified)==8651, ...
        'nylatest:ModelSchema','Unexpected latest-model axes or qualification cohort.');
    cached_receipt=proof;signature=current;
end
model=cached;receipt=cached_receipt;
end

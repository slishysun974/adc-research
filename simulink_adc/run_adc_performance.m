function run_adc_performance(run_folder)
% Native ADC simulation. Python learned states/outputs never seed this model.
folder=fileparts(mfilename('fullpath'));
reference_folder=fullfile(run_folder,'reference');
output_folder=fullfile(run_folder,'simulink');
assert(~exist(output_folder,'dir'),'Preserve existing native run');
mkdir(output_folder);
manifest=jsondecode(fileread(fullfile(reference_folder,'manifest.json')));
load_system(fullfile(folder,'adc_behavioral.slx'));
model='adc_behavioral';
cleanup=onCleanup(@()close_system(model,0)); % Leave saved demo untouched.
audit=audit_adc_model();
groups={'stimulus_trace','physical_trace','digital_trace','learning_trace'};
state=ones(1,8); splitstate=ones(1,8); states=struct('conversions',{},'coefficients',{});
whole=struct(); first=struct();
for j=1:numel(manifest.cases)
    entry=manifest.cases(j);
    if strcmp(entry.name,'preflight_whole') || strcmp(entry.name,'preflight_a')
        initial=ones(1,8);
    elseif strcmp(entry.name,'preflight_b')
        initial=splitstate;
    else
        initial=state;
    end
    entry.parameters.initial1=initial(1:4);
    entry.parameters.initial2=initial(5:8);
    adc_load_case(model,reference_folder,entry);
    fprintf('Simulink %d/%d: %s (%d conversions)\n',j,numel(manifest.cases),entry.name,entry.samples);
    result=sim(model);
    trace=struct();
    for g=1:numel(groups)
        values=result.get(groups{g});
        if ndims(values)==3
            values=reshape(permute(values,[3 1 2]),entry.samples,[]);
        end
        assert(size(values,1)==entry.samples && all(isfinite(values),'all'));
        trace.(groups{g})=values;
        handle=fopen(fullfile(output_folder,[entry.name '_' groups{g} '.bin']),'w','ieee-le');
        assert(handle>=0);
        fwrite(handle,values.','double'); fclose(handle);
    end
    if strcmp(entry.name,'preflight_whole')
        whole=trace;
    elseif strcmp(entry.name,'preflight_a')
        first=trace; splitstate=trace.learning_trace(end,9:16);
    elseif strcmp(entry.name,'preflight_b')
        assert(isequal(whole.physical_trace,[first.physical_trace; trace.physical_trace]));
        assert(isequal(whole.digital_trace,[first.digital_trace; trace.digital_trace]));
        assert(isequal(whole.learning_trace(:,9:16),[first.learning_trace(:,9:16); trace.learning_trace(:,9:16)]));
        fprintf('Native continuous/chunk preflight passed.\n');
    elseif strcmp(entry.kind,'train')
        state=trace.learning_trace(end,9:16);
    elseif strcmp(entry.kind,'test')
        assert(isequal(state,trace.learning_trace(end,9:16)),'Frozen evaluation changed banks');
        states(end+1)=struct('conversions',entry.offset,'coefficients',state); %#ok<AGROW>
    end
end
write_json(fullfile(output_folder,'states.json'),states);
execution=struct('matlab_version',version,'simulink_version',ver('simulink'), ...
    'solver',get_param(model,'Solver'),'fixed_step',get_param(model,'FixedStep'), ...
    'model_audit',audit,'chunk_preflight_passed',true, ...
    'bank_source','Own previous native training chunk; unity initial state; no reference states consumed', ...
    'model_saved',false);
write_json(fullfile(output_folder,'execution.json'),execution);
fprintf('Native performance run complete.\n');
end

function write_json(file,value)
handle=fopen(file,'w','n','UTF-8');
assert(handle>=0); fprintf(handle,'%s\n',jsonencode(value,PrettyPrint=true)); fclose(handle);
end

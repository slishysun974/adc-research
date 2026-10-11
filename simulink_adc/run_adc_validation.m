function run_adc_validation(reference_folder,output_folder)
% Execute the independent Simulink model; every trace goes to a separate CSV.
folder=fileparts(mfilename('fullpath'));
if nargin < 1, reference_folder=fullfile(folder,'outputs','reference'); end
if nargin < 2, output_folder=fullfile(folder,'outputs','simulink'); end
if ~exist(output_folder,'dir'), mkdir(output_folder); end
manifest=jsondecode(fileread(fullfile(reference_folder,'manifest.json')));
primitives=validate_adc_primitives(reference_folder);
load_system(fullfile(folder,'adc_behavioral.slx'));
model='adc_behavioral';
audit=audit_adc_model();
groups={'stimulus_trace','physical_trace','digital_trace','learning_trace'};
for j=1:numel(manifest.cases)
    entry=manifest.cases(j);
    adc_load_case(model,reference_folder,entry);
    fprintf('Simulink %d/%d: %s (%d conversions)\n',j,numel(manifest.cases),entry.name,entry.samples);
    result=sim(model);
    for g=1:numel(groups)
        values=result.get(groups{g});
        if ndims(values)==3
            % MATLAB matrix-valued signals are [rows,columns,time].
            values=reshape(permute(values,[3 1 2]),entry.samples,[]);
        end
        assert(size(values,1)==entry.samples,'Unexpected sample count for %s',entry.name);
        file=fullfile(output_folder,[entry.name '_' groups{g} '.csv']);
        handle=fopen(file,'w');
        cleanup=onCleanup(@()fclose(handle));
        format=[repmat('%.17g,',1,size(values,2)-1) '%.17g\n'];
        fprintf(handle,format,values.');
        clear cleanup
    end
end
% A new sim call must clear persistent accumulators and analog/digital delays.
repeat=sim(model);
for g=1:numel(groups)
    assert(isequal(result.get(groups{g}),repeat.get(groups{g})), ...
        'Restart did not reset %s',groups{g});
end
execution=struct('matlab_version',version,'simulink_version',ver('simulink'), ...
    'solver',get_param(model,'Solver'),'fixed_step',get_param(model,'FixedStep'), ...
    'model_blocks',audit.model_blocks,'model_audit',audit, ...
    'restart_identical',true,'primitives',primitives);
handle=fopen(fullfile(output_folder,'execution.json'),'w');
fprintf(handle,'%s\n',jsonencode(execution,PrettyPrint=true)); fclose(handle);
% Leave the saved, embedded demo in the model, independent of output folders.
demo=manifest.cases(strcmp({manifest.cases.name},'demo_tone'));
adc_load_case(model,reference_folder,demo);
save_system(model);
render_adc_previews(output_folder);
render_adc_results(reference_folder,output_folder);
fprintf('All Simulink cases executed; compare with python_reference.py compare.\n');
end

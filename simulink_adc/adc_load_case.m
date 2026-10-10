function C = adc_load_case(model,reference_folder,entry)
% Only parameters and input stimuli enter the model workspace.
C=entry.parameters;
fields=fieldnames(C);
for j=1:numel(fields)
    if isnumeric(C.(fields{j})) && ~isscalar(C.(fields{j}))
        C.(fields{j})=reshape(C.(fields{j}),1,[]);
    end
end
stimulus=readmatrix(fullfile(reference_folder,[entry.name '_input.csv']));
workspace=get_param(model,'ModelWorkspace');
assignin(workspace,'C',C);
assignin(workspace,'n_signal',[stimulus(:,1) stimulus(:,1)]);
assignin(workspace,'x_signal',stimulus(:,1:2));
assignin(workspace,'d1_signal',stimulus(:,[1 3]));
assignin(workspace,'d2_signal',stimulus(:,[1 4]));
set_param(model,'StartTime','0','StopTime',num2str(size(stimulus,1)-1));
end

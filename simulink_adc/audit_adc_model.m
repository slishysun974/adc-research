function result=audit_adc_model()
% Verify embedded code, independent inputs and explicit feedback state.
folder=fileparts(mfilename('fullpath'));
model='adc_behavioral';
load_system(fullfile(folder,[model '.slx']));
root=sfroot;
charts=root.find('-isa','Stateflow.EMChart');
checked=0;
for j=1:numel(charts)
    if startsWith(charts(j).Path,[model '/'])
        token=regexp(charts(j).Script,'function\s+(?:\[[^\]]*\]|\w+)\s*=\s*(\w+)','tokens','once');
        assert(~isempty(token));
        expected=fileread(fullfile(folder,'blocks',[token{1} '.m']));
        assert(strcmp(charts(j).Script,expected),'Embedded function differs: %s',charts(j).Path);
        checked=checked+1;
    end
end
assert(checked==16);
sources=find_system(model,'LookUnderMasks','all','BlockType','FromWorkspace');
variables=cellfun(@(p)get_param(p,'VariableName'),sources,'UniformOutput',false);
assert(isequal(sort(variables(:)),sort({'x_signal';'d1_signal';'d2_signal';'n_signal'})));
workspace=get_param(model,'ModelWorkspace');
for j=1:numel(variables), assert(evalin(workspace,['exist(''' variables{j} ''',''var'')'])==1); end
delays=find_system(model,'LookUnderMasks','all','BlockType','UnitDelay');
assert(numel(delays)==5);
for j=1:numel(delays), assert(strcmp(get_param(delays{j},'SampleTime'),'1')); end
assert(strcmp(get_param(model,'Solver'),'FixedStepDiscrete'));
assert(strcmp(get_param(model,'FixedStep'),'1'));
% Inspect the saved model itself, including native blocks and routed signals.
% A single top-level digital subsystem contains two distinct stage inverses.
edges={
    model,'Stage_1',1,'Stage_2',1;
    model,'Stage_1',3,'Auxiliary_path',1;
    model,'Stage_1',1,'Auxiliary_path',2;
    model,'Auxiliary_path',1,'Stage_2',2;
    model,'Stage_2',1,'SAR_8bit',1;
    model,'Stage_1',2,'Digital_correction',1;
    model,'Stage_2',2,'Digital_correction',2;
    model,'SAR_8bit',2,'Digital_correction',3;
    model,'Gu_background_update',1,'Digital_correction',6;
    model,'Gu_background_update',2,'Digital_correction',7;
    model,'Digital_correction',5,'Gu_background_update',1;
    model,'Digital_correction',6,'Gu_background_update',2;
    model,'Digital_correction',7,'Gu_background_update',3;
    model,'Digital_correction',8,'Gu_background_update',4;
    [model '/Digital_correction'],'backend_centered',1,'PWL_stage_2',1;
    [model '/Digital_correction'],'k2',1,'PWL_stage_2',2;
    [model '/Digital_correction'],'Coarse_2',1,'Raw_stage_1',1;
    [model '/Digital_correction'],'PWL_stage_2',1,'Raw_stage_1',2;
    [model '/Digital_correction'],'Dither_copy_2',1,'Raw_stage_1',3;
    [model '/Digital_correction'],'Raw_stage_1',1,'PWL_stage_1',1;
    [model '/Digital_correction'],'k1',1,'PWL_stage_1',2;
    [model '/Digital_correction'],'PWL_stage_1',1,'Local_learning_1',1;
    [model '/Digital_correction'],'Dither_copy_1',1,'Local_learning_1',2;
    [model '/Digital_correction'],'PWL_stage_2',1,'Local_learning_2',1;
    [model '/Digital_correction'],'Dither_copy_2',1,'Local_learning_2',2;
    [model '/Digital_correction'],'Coarse_1',1,'Centered_corrected',1;
    [model '/Digital_correction'],'PWL_stage_1',1,'Centered_corrected',2;
    [model '/Digital_correction'],'Dither_copy_1',1,'Centered_corrected',3;
    [model '/Gu_background_update'],'Coefficient_bank_1',1,'Gates_1',1;
    [model '/Gu_background_update'],'Coefficient_bank_2',1,'Gates_2',1;
    [model '/Gu_background_update'],'local1',1,'Gates_1',4;
    [model '/Gu_background_update'],'local2',1,'Gates_2',4;
    [model '/Gu_background_update'],'D1',1,'Gates_1',3;
    [model '/Gu_background_update'],'D2',1,'Gates_2',3;
    [model '/Gu_background_update'],'Window_accumulate_commit',1,'Coefficient_bank_1',1;
    [model '/Gu_background_update'],'Window_accumulate_commit',2,'Coefficient_bank_2',1;
    [model '/Gu_background_update'],'Coefficient_bank_1',1,'k1',1;
    [model '/Gu_background_update'],'Coefficient_bank_2',1,'k2',1};
for j=1:size(edges,1), assert_connected(edges{j,:}); end
for index=1:2
    path=sprintf('%s/Stage_%d',model,index);
    assert_connected(path,'auxiliary',1,'Flash',1);
    assert_connected(path,'main',1,'Residue_sum',1);
    assert(strcmp(get_param([path '/Residue_sum'],'Inputs'),'+-+'));
end
digital=[model '/Digital_correction'];
assert(strcmp(get_param([digital '/Raw_stage_1'],'Inputs'),'++-'));
assert(strcmp(get_param([digital '/Centered_corrected'],'Inputs'),'++-'));
assert(strcmp(get_param([digital '/Local_learning_1'],'Inputs'),'+-'));
assert(strcmp(get_param([digital '/Local_learning_2'],'Inputs'),'+-'));
assert(strcmp(get_param([digital '/Width_1'],'Value'),'128'));
assert(strcmp(get_param([digital '/Width_2'],'Value'),'32'));
assert(strcmp(get_param([digital '/Coarse_1'],'Gain'),'512'));
assert(strcmp(get_param([digital '/Coarse_2'],'Gain'),'128'));
C=evalin(workspace,'C');
assert(numel(C.initial1)==4 && numel(C.initial2)==4);
result=struct('passed',true,'embedded_functions',checked,'stimulus_sources',numel(sources), ...
    'feedback_delays',numel(delays),'model_blocks',numel(find_system(model,'LookUnderMasks','all','Type','Block')), ...
    'signal_topology_edges',size(edges,1)+4,'pwl_stages',2,'coefficient_banks',2, ...
    'coefficients_per_bank',4,'default_digital_mode',C.digital_mode, ...
    'default_auxiliary_mode',C.aux_parameters(1));
fprintf('Model code/input/state audit: PASS\n');
end

function assert_connected(system,source,source_port,destination,destination_port)
ports=get_param([system '/' destination],'PortHandles');
line=get_param(ports.Inport(destination_port),'Line');
assert(line~=-1,'Unconnected input: %s/%s/%d',system,destination,destination_port);
assert(get_param(line,'SrcBlockHandle')==get_param([system '/' source],'Handle'), ...
    'Wrong source block: %s/%s/%d',system,destination,destination_port);
port=get_param(line,'SrcPortHandle');
assert(get_param(port,'PortNumber')==source_port, ...
    'Wrong source port: %s/%s/%d',system,destination,destination_port);
end
